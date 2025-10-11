"""This module defines the core service for handling procurement analyses."""

import hashlib
import json
import os
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from public_detective.constants.analysis_feedback import ExclusionReason, PrioritizationLogic, Warnings
from public_detective.exceptions.analysis import AnalysisError
from public_detective.models.analyses import AnalysisResult
from public_detective.models.file_records import NewFileRecord
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.models.procurements import Procurement
from public_detective.models.source_documents import NewSourceDocument
from public_detective.providers.ai import AiProvider
from public_detective.providers.config import Config, ConfigProvider
from public_detective.providers.gcs import GcsProvider
from public_detective.providers.logging import Logger, LoggingProvider
from public_detective.providers.pubsub import PubSubProvider
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.repositories.budget_ledger import BudgetLedgerRepository
from public_detective.repositories.file_records import FileRecordsRepository
from public_detective.repositories.procurements import ProcessedFile, ProcurementsRepository
from public_detective.repositories.source_documents import SourceDocumentsRepository
from public_detective.repositories.status_history import StatusHistoryRepository
from public_detective.services.converter import ConverterService
from public_detective.services.pricing_service import Modality, PricingService
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AIFileCandidate(BaseModel):
    """Represents a file being considered for AI analysis."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    synthetic_id: str
    raw_document_metadata: dict
    original_path: str
    original_content: bytes
    ai_path: str = ""
    ai_content: bytes | list[bytes] = b""
    ai_gcs_uris: list[str] = Field(default_factory=list)
    prepared_content_gcs_uris: list[str] | None = None
    is_included: bool = False
    exclusion_reason: str | None = None
    file_record_id: UUID | None = None

    @model_validator(mode="after")
    def set_ai_defaults(self) -> "AIFileCandidate":
        """Set the ai_path and ai_content if they're not provided.

        Returns:
            AIFileCandidate: The instance itself, with `ai_path` and `ai_content` updated if they were not provided.
        """
        if not self.ai_path:
            self.ai_path = self.original_path
        if not self.ai_content:
            self.ai_content = self.original_content
        return self


class AnalysisService:
    """Orchestrates the entire procurement analysis pipeline."""

    procurement_repo: ProcurementsRepository
    analysis_repo: AnalysisRepository
    source_document_repo: SourceDocumentsRepository
    file_record_repo: FileRecordsRepository
    status_history_repo: StatusHistoryRepository
    budget_ledger_repo: BudgetLedgerRepository
    ai_provider: AiProvider
    gcs_provider: GcsProvider
    converter_service: ConverterService
    pubsub_provider: PubSubProvider | None
    logger: Logger
    config: Config
    pricing_service: PricingService

    _SUPPORTED_EXTENSIONS = (
        ".pdf",
        ".docx",
        ".doc",
        ".rtf",
        ".xlsx",
        ".xls",
        ".xlsb",
        ".csv",
        ".txt",
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".mp3",
        ".wav",
        ".flac",
        ".ogg",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".html",
        ".xml",
        ".json",
        ".txt",
        ".md",
    )
    _VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv")
    _AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".ogg")
    _IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp")
    _SPREADSHEET_EXTENSIONS = (".xlsx", ".xls", ".xlsb")
    _FILE_PRIORITY_ORDER = [
        "edital",
        "termo de referencia",
        "projeto basico",
        "planilha",
        "orcamento",
        "custos",
        "contrato",
        "ata de registro",
    ]

    def __init__(
        self,
        procurement_repo: ProcurementsRepository,
        analysis_repo: AnalysisRepository,
        source_document_repo: SourceDocumentsRepository,
        file_record_repo: FileRecordsRepository,
        status_history_repo: StatusHistoryRepository,
        budget_ledger_repo: BudgetLedgerRepository,
        ai_provider: AiProvider,
        gcs_provider: GcsProvider,
        pubsub_provider: PubSubProvider | None = None,
        gcs_path_prefix: str | None = None,
    ) -> None:
        """Initializes the service with its dependencies.

        Args:
            procurement_repo: The repository for procurement data.
            analysis_repo: The repository for analysis data.
            source_document_repo: The repository for source document data.
            file_record_repo: The repository for file record data.
            status_history_repo: The repository for status history data.
            budget_ledger_repo: The repository for budget ledger data.
            ai_provider: The provider for AI services.
            gcs_provider: The provider for Google Cloud Storage services.
            pubsub_provider: The provider for Pub/Sub services.
            gcs_path_prefix: Overwrites the base GCS path for uploads.
        """
        self.procurement_repo = procurement_repo
        self.analysis_repo = analysis_repo
        self.source_document_repo = source_document_repo
        self.file_record_repo = file_record_repo
        self.status_history_repo = status_history_repo
        self.budget_ledger_repo = budget_ledger_repo
        self.ai_provider = ai_provider
        self.gcs_provider = gcs_provider
        self.converter_service = ConverterService()
        self.pubsub_provider = pubsub_provider
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()
        self.pricing_service = PricingService()
        self.gcs_path_prefix = gcs_path_prefix

    def _get_modality(self, candidates: list[AIFileCandidate]) -> Modality:
        """Determines the modality of an analysis based on file extensions.

        Args:
            candidates: A list of AIFileCandidate objects.

        Returns:
            The modality of the analysis.
        """
        for candidate in candidates:
            ext = os.path.splitext(candidate.ai_path)[1].lower()
            if ext in self._VIDEO_EXTENSIONS:
                return Modality.VIDEO
            if ext in self._AUDIO_EXTENSIONS:
                return Modality.AUDIO
            if ext in self._IMAGE_EXTENSIONS:
                return Modality.IMAGE
        return Modality.TEXT

    def _update_status_with_history(
        self,
        analysis_id: UUID,
        status: ProcurementAnalysisStatus,
        details: str | None = None,
    ) -> None:
        """Updates the analysis status and records the change in the history table.

        Args:
            analysis_id: The ID of the analysis to update.
            status: The new status of the analysis.
            details: Additional details about the status change.
        """
        self.analysis_repo.update_analysis_status(analysis_id, status)
        self.status_history_repo.create_record(analysis_id, status, details)

    def process_analysis_from_message(self, analysis_id: UUID, max_output_tokens: int | None = None) -> None:
        """Processes a single analysis request received from a message queue.

        Args:
            analysis_id: The ID of the analysis to process.
            max_output_tokens: The maximum number of output tokens for the AI model.
        """
        try:
            analysis = self.analysis_repo.get_analysis_by_id(analysis_id)
            if not analysis:
                self.logger.error(f"Analysis with ID {analysis_id} not found.")
                return

            procurement = self.procurement_repo.get_procurement_by_id_and_version(
                analysis.procurement_control_number, analysis.version_number
            )
            if not procurement:
                self.logger.error(
                    f"Procurement {analysis.procurement_control_number} version {analysis.version_number} not found."
                )
                return

            try:
                self.analyze_procurement(procurement, analysis.version_number, analysis_id, max_output_tokens)
                self._update_status_with_history(
                    analysis_id, ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL, "Analysis completed successfully."
                )
            except Exception as e:
                self.logger.error(f"Analysis pipeline failed for analysis {analysis_id}: {e}", exc_info=True)
                self._update_status_with_history(analysis_id, ProcurementAnalysisStatus.ANALYSIS_FAILED, str(e))
                raise
        except Exception as e:
            raise AnalysisError(f"Failed to process analysis from message: {e}") from e

    def analyze_procurement(
        self,
        procurement: Procurement,
        version_number: int,
        analysis_id: UUID,
        max_output_tokens: int | None = None,
    ) -> None:
        """Executes the full analysis pipeline for a single procurement.

        Args:
            procurement: The procurement to analyze.
            version_number: The version number of the procurement.
            analysis_id: The ID of the analysis.
            max_output_tokens: The maximum number of output tokens for the AI model.
        """
        control_number = procurement.pncp_control_number
        self.logger.info(f"Starting analysis for procurement {control_number} version {version_number}...")

        procurement_id = self.procurement_repo.get_procurement_uuid(procurement.pncp_control_number, version_number)
        if not procurement_id:
            raise AnalysisError(f"Could not find procurement UUID for {control_number} v{version_number}")

        processed_files = self.procurement_repo.process_procurement_documents(procurement)
        if not processed_files:
            self.logger.warning(f"No files found for {control_number}. Aborting.")
            return

        all_candidates = self._prepare_ai_candidates(processed_files)

        source_docs_map = self._process_and_save_source_documents(analysis_id, all_candidates)
        self._upload_and_save_initial_records(procurement_id, analysis_id, all_candidates, source_docs_map)

        final_candidates, warnings = self._select_files_by_token_limit(all_candidates, procurement)
        self._update_selected_file_records(final_candidates)

        files_for_ai_uris = [
            uri for candidate in final_candidates if candidate.is_included for uri in candidate.ai_gcs_uris
        ]
        if not files_for_ai_uris:
            self.logger.error(f"No supported files left after filtering for {control_number}.")
            return

        files_for_hash = [
            (candidate.ai_path, candidate.ai_content) for candidate in final_candidates if candidate.is_included
        ]
        document_hash = self._calculate_hash(files_for_hash)
        modality = self._get_modality(final_candidates)

        try:
            prompt = self._build_analysis_prompt(procurement, final_candidates, warnings)
            ai_analysis, input_tokens, output_tokens, thinking_tokens = self.ai_provider.get_structured_analysis(
                prompt=prompt, file_uris=files_for_ai_uris, max_output_tokens=max_output_tokens
            )

            gcs_base_path = f"{procurement_id}/{analysis_id}"

            final_result = AnalysisResult(
                procurement_control_number=control_number,
                version_number=version_number,
                ai_analysis=ai_analysis,
                warnings=warnings,
                document_hash=document_hash,
                original_documents_gcs_path=gcs_base_path,
                processed_documents_gcs_path=None,
                analysis_prompt=prompt,
            )
            input_cost, output_cost, thinking_cost, total_cost = self.pricing_service.calculate(
                input_tokens, output_tokens, thinking_tokens, modality=modality
            )
            self.analysis_repo.save_analysis(
                analysis_id=analysis_id,
                result=final_result,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thinking_tokens=thinking_tokens,
                input_cost=input_cost,
                output_cost=output_cost,
                thinking_cost=thinking_cost,
                total_cost=total_cost,
            )

            self.budget_ledger_repo.save_expense(
                analysis_id,
                total_cost,
                f"Análise da licitação {procurement.pncp_control_number} (v{version_number}).",
            )

            self.logger.info(f"Successfully completed analysis for {control_number}.")

        except Exception as e:
            self.logger.error(f"Analysis pipeline failed for {control_number}: {e}", exc_info=True)
            raise

    def _prepare_ai_candidates(self, all_files: list[ProcessedFile]) -> list[AIFileCandidate]:
        """Prepares a list of AIFileCandidate objects from raw file data.

        Args:
            all_files: A list of `ProcessedFile` objects from the repository.

        Returns:
            A list of AIFileCandidate objects.
        """
        candidates = []
        for processed_file in all_files:
            candidate = AIFileCandidate(
                synthetic_id=processed_file.source_document_id,
                raw_document_metadata=processed_file.raw_document_metadata,
                original_path=processed_file.relative_path,
                original_content=processed_file.content,
            )
            ext = os.path.splitext(processed_file.relative_path)[1].lower()

            if ext not in self._SUPPORTED_EXTENSIONS:
                candidate.exclusion_reason = ExclusionReason.UNSUPPORTED_EXTENSION
                candidates.append(candidate)
                continue

            try:
                if ext == ".docx":
                    converted_content = self.converter_service.docx_to_html(processed_file.content)
                    candidate.ai_content = converted_content.encode("utf-8")
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.html"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext == ".rtf":
                    converted_content = self.converter_service.rtf_to_text(processed_file.content)
                    candidate.ai_content = converted_content.encode("utf-8")
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.txt"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext == ".doc":
                    converted_content = self.converter_service.doc_to_text(processed_file.content)
                    candidate.ai_content = converted_content.encode("utf-8")
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.txt"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext == ".bmp":
                    converted_content = self.converter_service.bmp_to_png(processed_file.content)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.png"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext == ".gif":
                    converted_content = self.converter_service.gif_to_mp4(processed_file.content)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.mp4"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext in (".xml", ".json"):
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.txt"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext in self._SPREADSHEET_EXTENSIONS:
                    converted_sheets = self.converter_service.spreadsheet_to_csvs(processed_file.content, ext)
                    all_csv_content = []
                    converted_paths = []
                    for sheet_name, sheet_content in converted_sheets:
                        base_name = os.path.splitext(os.path.basename(processed_file.relative_path))[0]
                        csv_filename = f"{base_name}_{sheet_name}.csv"
                        converted_paths.append(csv_filename)
                        all_csv_content.append(sheet_content)

                    candidate.ai_content = all_csv_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.csv"
                    candidate.prepared_content_gcs_uris = converted_paths

            except Exception as e:
                self.logger.error(f"Failed to process file {processed_file.relative_path}: {e}", exc_info=True)
                candidate.exclusion_reason = ExclusionReason.CONVERSION_FAILED

            candidates.append(candidate)
        return candidates

    def _select_files_by_token_limit(
        self, candidates: list[AIFileCandidate], procurement: Procurement
    ) -> tuple[list[AIFileCandidate], list[str]]:
        """Selects which files to include based on the AI model's token limit.

        Args:
            candidates: A list of AIFileCandidate objects to select from.
            procurement: The procurement being analyzed.

        Returns:
            A tuple containing the list of selected candidates and a list of warnings.
        """
        candidates.sort(key=lambda candidate: self._get_priority(candidate.original_path))
        max_tokens = self.config.GCP_GEMINI_MAX_INPUT_TOKENS
        warnings = []

        base_prompt_text = self._build_analysis_prompt(procurement, candidates, [])
        files_for_ai_uris: list[str] = []
        for candidate in candidates:
            if candidate.exclusion_reason:
                continue

            uris_to_test = files_for_ai_uris + candidate.ai_gcs_uris
            tokens, _, _ = self.ai_provider.count_tokens_for_analysis(base_prompt_text, uris_to_test)

            if tokens <= max_tokens:
                files_for_ai_uris.extend(candidate.ai_gcs_uris)
                candidate.is_included = True
            else:
                candidate.exclusion_reason = ExclusionReason.TOKEN_LIMIT_EXCEEDED.format(max_tokens=max_tokens)

        excluded_names = [
            os.path.basename(candidate.original_path) for candidate in candidates if not candidate.is_included
        ]
        if excluded_names:
            warnings.append(
                Warnings.TOKEN_LIMIT_EXCEEDED.format(max_tokens=max_tokens, ignored_files=", ".join(excluded_names))
            )

        return candidates, warnings

    def _process_and_save_source_documents(
        self,
        analysis_id: UUID,
        candidates: list[AIFileCandidate],
    ) -> dict[str, UUID]:
        """Saves unique source documents to the database.

        Args:
            analysis_id: The ID of the current analysis.
            candidates: A list of all file candidates.

        Returns:
            A dictionary mapping synthetic source document IDs to their new database UUIDs.
        """
        source_docs_map: dict[str, UUID] = {}
        unique_source_docs = {c.synthetic_id: c.raw_document_metadata for c in candidates}

        for synthetic_id, raw_meta in unique_source_docs.items():
            doc_model = NewSourceDocument(
                analysis_id=analysis_id,
                synthetic_id=str(synthetic_id),
                title=raw_meta.get("titulo", "N/A"),
                publication_date=raw_meta.get("dataPublicacaoPncp"),
                document_type_name=raw_meta.get("tipoDocumentoNome"),
                url=raw_meta.get("url"),
                raw_metadata=raw_meta,
            )
            db_id = self.source_document_repo.save_source_document(doc_model)
            source_docs_map[synthetic_id] = db_id
        return source_docs_map

    def _update_selected_file_records(self, candidates: list[AIFileCandidate]) -> None:
        """Updates the database records for files that were selected for analysis.

        Args:
            candidates: The list of candidates after the selection process.
        """
        selected_file_ids = [
            candidate.file_record_id for candidate in candidates if candidate.is_included and candidate.file_record_id
        ]
        if selected_file_ids:
            self.file_record_repo.set_files_as_included(selected_file_ids)

    def _upload_and_save_initial_records(
        self,
        procurement_id: UUID,
        analysis_id: UUID,
        candidates: list[AIFileCandidate],
        source_docs_map: dict[str, UUID],
    ) -> None:
        """Uploads all files to GCS and saves their initial metadata records.

        This method uploads both original and prepared files, populates the
        candidate objects with real GCS URIs, and saves the initial file
        record to the database with `included_in_analysis` set to False.

        Args:
            procurement_id: The database UUID of the procurement.
            analysis_id: The ID of the current analysis.
            candidates: A list of AIFileCandidate objects to upload and save.
            source_docs_map: A map of synthetic source IDs to database UUIDs.
        """
        bucket_name = self.config.GCP_GCS_BUCKET_PROCUREMENTS
        for candidate in candidates:
            source_document_db_id = source_docs_map[candidate.synthetic_id]
            standard_path = f"{procurement_id}/{analysis_id}/{source_document_db_id}"
            base_gcs_path = f"{self.gcs_path_prefix}/{standard_path}" if self.gcs_path_prefix else standard_path
            original_gcs_path = f"{base_gcs_path}/{os.path.basename(candidate.original_path)}"

            self.gcs_provider.upload_file(
                bucket_name=bucket_name,
                destination_blob_name=original_gcs_path,
                content=candidate.original_content,
                content_type="application/octet-stream",
            )

            final_converted_uris = []
            if candidate.prepared_content_gcs_uris:
                if isinstance(candidate.ai_content, list):
                    for i, prepared_path in enumerate(candidate.prepared_content_gcs_uris):
                        prepared_gcs_path = f"{base_gcs_path}/prepared_content/{prepared_path}"
                        self.gcs_provider.upload_file(
                            bucket_name=bucket_name,
                            destination_blob_name=prepared_gcs_path,
                            content=candidate.ai_content[i],
                            content_type="text/csv",
                        )
                        final_converted_uris.append(f"gs://{bucket_name}/{prepared_gcs_path}")
                else:
                    prepared_gcs_path = f"{base_gcs_path}/prepared_content/{os.path.basename(candidate.ai_path)}"
                    self.gcs_provider.upload_file(
                        bucket_name=bucket_name,
                        destination_blob_name=prepared_gcs_path,
                        content=candidate.ai_content,
                        content_type="application/octet-stream",
                    )
                    final_converted_uris.append(f"gs://{bucket_name}/{prepared_gcs_path}")

                candidate.ai_gcs_uris = final_converted_uris
                candidate.prepared_content_gcs_uris = final_converted_uris
            else:
                candidate.ai_gcs_uris = [f"gs://{bucket_name}/{original_gcs_path}"]

            file_record = NewFileRecord(
                source_document_id=source_document_db_id,
                file_name=os.path.basename(candidate.original_path),
                gcs_path=original_gcs_path,
                extension=os.path.splitext(candidate.original_path)[1].lstrip("."),
                size_bytes=len(candidate.original_content),
                nesting_level=candidate.original_path.count(os.sep),
                included_in_analysis=False,
                exclusion_reason=candidate.exclusion_reason,
                prioritization_logic=self._get_priority_as_string(candidate.original_path),
                prepared_content_gcs_uris=candidate.prepared_content_gcs_uris,
            )
            candidate.file_record_id = self.file_record_repo.save_file_record(file_record)

    def _get_priority(self, file_path: str) -> int:
        """Determines the priority of a file based on keywords in its name.

        Args:
            file_path: The path of the file to prioritize.

        Returns:
            The priority of the file as an integer.
        """
        path_lower = file_path.lower()
        for i, keyword in enumerate(self._FILE_PRIORITY_ORDER):
            if keyword in path_lower:
                return i
        return len(self._FILE_PRIORITY_ORDER)

    def _get_priority_as_string(self, file_path: str) -> str:
        """Returns the priority keyword found in the file path.

        Args:
            file_path: The path of the file to prioritize.

        Returns:
            The priority keyword found in the file path.
        """
        path_lower = file_path.lower()
        for keyword in self._FILE_PRIORITY_ORDER:
            if keyword in path_lower:
                message: str = PrioritizationLogic.BY_KEYWORD.format(keyword=keyword)
                return message
        no_priority_message: str = PrioritizationLogic.NO_PRIORITY
        return no_priority_message

    def _build_analysis_prompt(
        self,
        procurement: Procurement,
        candidates: list[AIFileCandidate],
        warnings: list[str],
    ) -> str:
        """Constructs the prompt for the AI, including contextual warnings.

        Args:
            procurement: The procurement to build the prompt for.
            candidates: The list of file candidates for the analysis.
            warnings: A list of warnings to include in the prompt.

        Returns:
            The prompt for the AI.
        """
        procurement_json = procurement.model_dump_json(by_alias=True, indent=2)

        source_doc_files = defaultdict(list)
        for candidate in candidates:
            if candidate.is_included:
                source_doc_files[candidate.synthetic_id].append(candidate)

        document_context_parts = []
        for _source_id, files in source_doc_files.items():
            meta = files[0].raw_document_metadata
            title = meta.get("titulo", "N/A")
            doc_type = meta.get("tipoDocumentoNome", "N/A")
            pub_date = meta.get("dataPublicacaoPncp", "N/A")

            file_list = "\n".join([f"- `{os.path.basename(f.ai_path)}`" for f in files])

            context_part = (
                f"**Fonte do Documento:** {title} (Tipo: {doc_type}, Publicado em: {pub_date})\n"
                f"**Arquivos extraídos desta fonte:**\n{file_list}"
            )
            document_context_parts.append(context_part)

        document_context_section = "\n\n---\n\n".join(document_context_parts)

        warnings_section = ""
        if warnings:
            warnings_text = "\n- ".join(warnings)
            warnings_section = f"""
            --- ATENÇÃO ---
            Os seguintes problemas foram detectados ao preparar os arquivos.
            Considere estas limitações em sua análise:
            - {warnings_text}
            --- FIM DOS AVISOS ---
            """

        return f"""
        Você é um auditor sênior especializado em licitações públicas no Brasil.
        Sua tarefa é analisar os documentos em anexo para identificar
        possíveis irregularidades no processo de licitação.
        {warnings_section}
        Primeiro, revise os metadados da licitação em formato JSON para obter o
        contexto geral. Em seguida, use a lista de documentos e arquivos para
        entender a origem de cada anexo.

        --- METADADOS DA LICITAÇÃO (JSON) ---
        {procurement_json}
        --- FIM DOS METADADOS ---

        --- CONTEXTO DOS DOCUMENTOS ANEXADOS ---
        {document_context_section}
        --- FIM DO CONTEXTO ---

        Com base em todas as informações disponíveis, analise a licitação em
        busca de irregularidades nas seguintes categorias. Para cada achado,
        você deve extrair a citação exata de um dos documentos que embase sua
        análise.

        1.  Direcionamento para Fornecedor Específico (DIRECIONAMENTO)
        2.  Restrição de Competitividade (RESTRICAO_COMPETITIVIDADE)
        3.  Potencial de Sobrepreço (SOBREPRECO)

        Após a análise, atribua uma nota de risco de 0 a 10 e forneça uma
        justificativa detalhada para essa nota (em pt-br).

        **Critérios para a Nota de Risco:**
        - **0-2 (Risco Baixo):** Nenhuma irregularidade significativa
          encontrada.
        - **3-5 (Risco Moderado):** Foram encontrados indícios de
          irregularidades, mas sem evidências conclusivas.
        - **6-8 (Risco Alto):** Evidências claras de irregularidades em uma ou
          mais categorias.
        - **9-10 (Risco Crítico):** Irregularidades graves e generalizadas, com
          forte suspeita de fraude.

        Sua resposta deve ser um objeto JSON que siga estritamente o esquema
        fornecido, incluindo os campos `procurement_summary`, `analysis_summary` e `risk_score_rationale`.

        Forneça um resumo conciso (em pt-br, máximo 3 sentenças) do escopo da licitação no campo `procurement_summary`.

        Forneça um resumo conciso (em pt-br, máximo 3 sentenças) da análise geral no campo `analysis_summary`.

        **Palavras-chave para SEO:**
        Finalmente, gere uma lista de 5 a 10 palavras-chave estratégicas (em pt-br)
        que um usuário interessado nesta licitação digitaria no Google. Pense em
        termos como o objeto da licitação, o órgão público, a cidade/estado, e
        possíveis sinônimos ou termos relacionados que maximizem a
        encontrabilidade desta análise.
        """

    def _calculate_hash(self, files: list[tuple[str, bytes | list[bytes]]]) -> str:
        """Calculates a SHA-256 hash from the content of a list of files.

        Args:
            files: A list of tuples containing the file path and content.

        Returns:
            The SHA-256 hash of the file content.
        """
        hasher = hashlib.sha256()
        for _, content in sorted(files, key=lambda x: x[0]):
            if isinstance(content, list):
                for item in content:
                    hasher.update(item)
            else:
                hasher.update(content)
        return hasher.hexdigest()

    def run_specific_analysis(self, analysis_id: UUID) -> None:
        """Triggers an analysis for a specific ID by publishing a message.

        Args:
            analysis_id: The ID of the analysis to trigger.
        """
        try:
            self.logger.info(f"Running specific analysis for analysis_id: {analysis_id}")
            analysis = self.analysis_repo.get_analysis_by_id(analysis_id)
            if not analysis:
                self.logger.error(f"Analysis with ID {analysis_id} not found.")
                return

            if analysis.status != ProcurementAnalysisStatus.PENDING_ANALYSIS.value:
                self.logger.warning(
                    f"Analysis {analysis_id} is not in PENDING_ANALYSIS state (current: {analysis.status}). Skipping."
                )
                return

            self._update_status_with_history(
                analysis_id, ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS, "Worker picked up the task."
            )

            if not self.pubsub_provider:
                raise ValueError("PubSubProvider is not configured for AnalysisService")

            message_data = {
                "procurement_control_number": analysis.procurement_control_number,
                "version_number": analysis.version_number,
                "analysis_id": str(analysis_id),
            }
            message_json = json.dumps(message_data)
            message_bytes = message_json.encode()
            self.pubsub_provider.publish(self.config.GCP_PUBSUB_TOPIC_PROCUREMENTS, message_bytes)
            self.logger.info(f"Published analysis request for analysis_id {analysis_id} to Pub/Sub.")
        except Exception as e:
            raise AnalysisError(f"An unexpected error occurred during specific analysis: {e}") from e

    def run_pre_analysis(
        self,
        start_date: date,
        end_date: date,
        batch_size: int,
        sleep_seconds: int,
        max_messages: int | None = None,
    ) -> list[tuple[Procurement, dict[str, Any]]]:
        """Runs the pre-analysis job for a given date range.

        Args:
            start_date: The start date of the date range.
            end_date: The end date of the date range.
            batch_size: The number of procurements to process in each batch.
            sleep_seconds: The number of seconds to sleep between batches.
            max_messages: The maximum number of messages to publish.

        Returns:
            A list of all procurements found.
        """
        try:
            self.logger.info(f"Starting pre-analysis job for date range: {start_date} to {end_date}")
            current_date = start_date
            messages_published_count = 0

            all_procurements = []
            while current_date <= end_date:
                procurements_with_raw = self.procurement_repo.get_updated_procurements_with_raw_data(
                    target_date=current_date
                )
                all_procurements.extend(procurements_with_raw)
                current_date += timedelta(days=1)

            for i in range(0, len(all_procurements), batch_size):
                batch = all_procurements[i : i + batch_size]
                self.logger.info(f"Processing batch with {len(batch)} procurements.")

                for procurement, raw_data in batch:
                    try:
                        self._pre_analyze_procurement(procurement, raw_data)
                        messages_published_count += 1
                        if max_messages is not None and messages_published_count >= max_messages:
                            self.logger.info(f"Reached max_messages ({max_messages}). Stopping pre-analysis.")
                            return all_procurements
                    except Exception as e:
                        self.logger.error(
                            f"Failed to pre-analyze procurement {procurement.pncp_control_number}: {e}",
                            exc_info=True,
                        )

                if i + batch_size < len(all_procurements):
                    self.logger.info(f"Sleeping for {sleep_seconds} seconds before next batch.")
                    time.sleep(sleep_seconds)

            self.logger.info("Pre-analysis job for the entire date range has been completed.")
            return all_procurements
        except Exception as e:
            raise AnalysisError(f"An unexpected error occurred during pre-analysis: {e}") from e

    def _pre_analyze_procurement(self, procurement: Procurement, raw_data: dict) -> None:
        """Performs the pre-analysis for a single procurement.

        Args:
            procurement: The procurement to pre-analyze.
            raw_data: The raw data of the procurement.
        """
        all_original_files = self.procurement_repo.process_procurement_documents(procurement)
        all_candidates = self._prepare_ai_candidates(all_original_files)
        final_candidates, _ = self._select_files_by_token_limit(all_candidates, procurement)
        files_for_ai = [(c.ai_path, c.ai_content) for c in final_candidates if c.is_included]

        raw_data_str = json.dumps(raw_data, sort_keys=True)
        all_files_content = b"".join(file.content for file in sorted(all_original_files, key=lambda x: x.relative_path))
        procurement_content_hash = hashlib.sha256(raw_data_str.encode("utf-8") + all_files_content).hexdigest()

        if self.procurement_repo.get_procurement_by_hash(procurement_content_hash):
            self.logger.info(f"Procurement with hash {procurement_content_hash} already exists. Skipping.")
            return

        analysis_document_hash = self._calculate_hash(files_for_ai)

        latest_version = self.procurement_repo.get_latest_version(procurement.pncp_control_number)
        new_version = latest_version + 1

        self.procurement_repo.save_procurement_version(
            procurement=procurement,
            raw_data=raw_data_str,
            version_number=new_version,
            content_hash=procurement_content_hash,
        )

        base_prompt_text = self._build_analysis_prompt(procurement, final_candidates, [])
        uris_for_token_count = [uri for c in final_candidates if c.is_included for uri in c.ai_gcs_uris]
        input_tokens, _, _ = self.ai_provider.count_tokens_for_analysis(base_prompt_text, uris_for_token_count)

        output_tokens = 0
        thinking_tokens = 0
        modality = self._get_modality(final_candidates)
        input_cost, output_cost, thinking_cost, total_cost = self.pricing_service.calculate(
            input_tokens, output_tokens, thinking_tokens, modality=modality
        )

        analysis_id = self.analysis_repo.save_pre_analysis(
            procurement_control_number=procurement.pncp_control_number,
            version_number=new_version,
            document_hash=analysis_document_hash,
            input_tokens_used=input_tokens,
            output_tokens_used=output_tokens,
            thinking_tokens_used=thinking_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            thinking_cost=thinking_cost,
            total_cost=total_cost,
        )
        self.status_history_repo.create_record(
            analysis_id, ProcurementAnalysisStatus.PENDING_ANALYSIS, "Pre-analysis completed."
        )

    def run_ranked_analysis(
        self,
        use_auto_budget: bool,
        budget_period: str | None,
        zero_vote_budget_percent: int,
        budget: Decimal | None = None,
        max_messages: int | None = None,
    ) -> list[Any]:
        """Runs the ranked analysis job.

        Args:
            use_auto_budget: Whether to use the auto-budget calculation.
            budget_period: The period for the auto-budget calculation.
            zero_vote_budget_percent: The percentage of the budget to use for zero-vote analyses.
            budget: The manual budget to use.
            max_messages: The maximum number of messages to publish.

        Returns:
            A list of analyses that were triggered.
        """
        if use_auto_budget:
            if not budget_period:
                raise ValueError("Budget period must be provided for auto-budget calculation.")
            execution_budget = self._calculate_auto_budget(budget_period)
        elif budget is not None:
            execution_budget = budget
        else:
            raise ValueError("Either a manual budget must be provided or auto-budget must be enabled.")

        self.logger.info(f"Starting ranked analysis job with a budget of {execution_budget:.2f} BRL.")
        if max_messages is not None:
            self.logger.info(f"Analysis run is limited to a maximum of {max_messages} message(s).")

        remaining_budget = execution_budget
        zero_vote_budget = execution_budget * (Decimal(zero_vote_budget_percent) / 100)
        self.logger.info(f"Zero-vote budget is {zero_vote_budget:.2f} BRL.")

        pending_analyses = self.analysis_repo.get_pending_analyses_ranked()
        self.logger.info(f"Found {len(pending_analyses)} pending analyses.")
        triggered_analyses: list[Any] = []

        for analysis in pending_analyses:
            if remaining_budget <= 0:
                self.logger.info("Budget exhausted. Stopping job.")
                break

            if max_messages is not None and len(triggered_analyses) >= max_messages:
                self.logger.info(f"Reached max_messages limit of {max_messages}. Stopping job.")
                break

            estimated_cost = analysis.total_cost or Decimal(0)

            if estimated_cost > remaining_budget:
                self.logger.info(
                    f"Skipping analysis {analysis.analysis_id}. "
                    f"Cost ({estimated_cost:.2f} BRL) exceeds remaining "
                    f"budget ({remaining_budget:.2f} BRL)."
                )
                continue

            if analysis.votes_count == 0 and estimated_cost > zero_vote_budget:
                self.logger.info(
                    f"Skipping zero-vote analysis {analysis.analysis_id}. "
                    f"Cost ({estimated_cost:.2f} BRL) exceeds remaining "
                    f"zero-vote budget ({zero_vote_budget:.2f} BRL)."
                )
                continue

            self.logger.info(
                f"Processing analysis {analysis.analysis_id} with " f"estimated cost of {estimated_cost:.2f} BRL."
            )
            try:
                self.run_specific_analysis(analysis.analysis_id)
                remaining_budget -= estimated_cost
                if analysis.votes_count == 0:
                    zero_vote_budget -= estimated_cost

                self.logger.info(
                    f"Analysis {analysis.analysis_id} triggered. "
                    f"Remaining budget: {remaining_budget:.2f} BRL. "
                    f"Zero-vote budget: {zero_vote_budget:.2f} BRL."
                )
                triggered_analyses.append(analysis)
            except Exception as e:
                self.logger.error(
                    f"Failed to trigger analysis {analysis.analysis_id}: {e}",
                    exc_info=True,
                )

        self.logger.info("Ranked analysis job completed.")
        return triggered_analyses

    def retry_analyses(self, initial_backoff_hours: int, max_retries: int, timeout_hours: int) -> int:
        """Retries failed or stale analyses.

        Args:
            initial_backoff_hours: The initial backoff in hours.
            max_retries: The maximum number of retries.
            timeout_hours: The timeout in hours.

        Returns:
            The number of analyses retried.
        """
        try:
            analyses_to_retry = self.analysis_repo.get_analyses_to_retry(max_retries, timeout_hours)
            retried_count = 0

            for analysis in analyses_to_retry:
                now = datetime.now(timezone.utc)
                last_updated = analysis.updated_at.replace(tzinfo=timezone.utc)
                backoff_hours = initial_backoff_hours * (2**analysis.retry_count)
                next_retry_time = last_updated + timedelta(hours=backoff_hours)

                if now >= next_retry_time:
                    self.logger.info(f"Retrying analysis {analysis.analysis_id}...")
                    modality = Modality.TEXT
                    input_cost, output_cost, thinking_cost, total_cost = self.pricing_service.calculate(
                        analysis.input_tokens_used,
                        analysis.output_tokens_used,
                        analysis.thinking_tokens_used,
                        modality=modality,
                    )
                    new_analysis_id = self.analysis_repo.save_retry_analysis(
                        procurement_control_number=analysis.procurement_control_number,
                        version_number=analysis.version_number,
                        document_hash=analysis.document_hash,
                        input_tokens_used=analysis.input_tokens_used,
                        output_tokens_used=analysis.output_tokens_used,
                        thinking_tokens_used=analysis.thinking_tokens_used,
                        input_cost=input_cost,
                        output_cost=output_cost,
                        thinking_cost=thinking_cost,
                        total_cost=total_cost,
                        retry_count=analysis.retry_count + 1,
                        analysis_prompt=analysis.analysis_prompt,
                    )
                    self.run_specific_analysis(new_analysis_id)
                    retried_count += 1

            return retried_count
        except Exception as e:
            raise AnalysisError(f"An unexpected error occurred during retry analyses: {e}") from e

    def get_procurement_overall_status(self, procurement_control_number: str) -> dict[str, Any] | None:
        """Retrieves the overall status of a procurement.

        Args:
            procurement_control_number: The control number of the procurement.

        Returns:
            The overall status of the procurement.
        """
        self.logger.info(f"Fetching overall status for procurement {procurement_control_number}.")
        status_info: dict[str, Any] | None = self.analysis_repo.get_procurement_overall_status(
            procurement_control_number
        )
        if not status_info:
            self.logger.warning(f"No overall status found for procurement {procurement_control_number}.")
            return None
        return status_info

    def _calculate_auto_budget(self, budget_period: str) -> Decimal:
        """Calculates the budget for the current run based on donation history and spending pace.

        Args:
            budget_period: The period for the auto-budget calculation.

        Returns:
            The calculated budget for the current run.
        """
        today = datetime.now(timezone.utc).date()
        if budget_period == "daily":
            start_of_period = today
            days_in_period = 1
            day_of_period = 1
        elif budget_period == "weekly":
            start_of_period = today - timedelta(days=today.weekday())
            days_in_period = 7
            day_of_period = today.weekday() + 1
        elif budget_period == "monthly":
            start_of_period = today.replace(day=1)
            next_month = start_of_period.replace(day=28) + timedelta(days=4)
            days_in_period = (next_month - timedelta(days=next_month.day)).day
            day_of_period = today.day
        else:
            raise ValueError(f"Invalid budget period: {budget_period}")

        current_balance = self.budget_ledger_repo.get_total_donations()
        expenses_in_period = self.budget_ledger_repo.get_total_expenses_for_period(start_of_period)
        period_capital = current_balance + expenses_in_period
        daily_target = period_capital / days_in_period
        cumulative_target_today = daily_target * day_of_period
        budget_for_this_run = cumulative_target_today - expenses_in_period

        self.logger.debug(
            f"Auto-budget calculation: Balance={current_balance:.2f}, "
            f"Expenses={expenses_in_period:.2f}, Capital={period_capital:.2f}, "
            f"DailyTarget={daily_target:.2f}, CumulativeTarget={cumulative_target_today:.2f}"
        )

        return Decimal(max(Decimal("0"), budget_for_this_run))
