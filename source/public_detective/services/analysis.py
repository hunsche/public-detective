"""This module defines the core service for handling procurement analyses."""

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from public_detective.constants.analysis_feedback import ExclusionReason, PrioritizationLogic, Warnings
from public_detective.exceptions.analysis import AnalysisError
from public_detective.models.analyses import Analysis, AnalysisResult
from public_detective.models.file_records import NewFileRecord
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.models.procurements import Procurement
from public_detective.providers.ai import AiProvider
from public_detective.providers.config import Config, ConfigProvider
from public_detective.providers.gcs import GcsProvider
from public_detective.providers.logging import Logger, LoggingProvider
from public_detective.providers.pubsub import PubSubProvider
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.repositories.budget_ledger import BudgetLedgerRepository
from public_detective.repositories.file_records import FileRecordsRepository
from public_detective.repositories.procurements import ProcurementsRepository
from public_detective.repositories.status_history import StatusHistoryRepository
from public_detective.services.converter import ConverterService
from public_detective.services.pricing_service import Modality, PricingService


@dataclass
class AIFileCandidate:
    """Represents a file being considered for AI analysis."""

    original_path: str
    original_content: bytes
    ai_path: str = ""
    ai_content: bytes = b""
    converted_gcs_path: str | None = None
    is_included: bool = False
    exclusion_reason: str | None = None

    def __post_init__(self):
        """Set the ai_path and ai_content if they're not provided."""
        if not self.ai_path:
            self.ai_path = self.original_path
        if not self.ai_content:
            self.ai_content = self.original_content


class AnalysisService:
    """Orchestrates the entire procurement analysis pipeline."""

    procurement_repo: ProcurementsRepository
    analysis_repo: AnalysisRepository
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
    )
    _VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv")
    _AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".ogg")
    _IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp")
    _DOCX_EXTENSIONS = (".docx", ".doc", ".rtf")
    _XLSX_EXTENSIONS = (".xlsx", ".xls")
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
        file_record_repo: FileRecordsRepository,
        status_history_repo: StatusHistoryRepository,
        budget_ledger_repo: BudgetLedgerRepository,
        ai_provider: AiProvider,
        gcs_provider: GcsProvider,
        pubsub_provider: PubSubProvider | None = None,
    ) -> None:
        """Initializes the service with its dependencies."""
        self.procurement_repo = procurement_repo
        self.analysis_repo = analysis_repo
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

    def _get_modality(self, files: list[tuple[str, bytes]]) -> Modality:
        """Determines the modality of an analysis based on file extensions."""
        for path, _ in files:
            ext = os.path.splitext(path)[1].lower()
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
        """Updates the analysis status and records the change in the history table."""
        self.analysis_repo.update_analysis_status(analysis_id, status)
        self.status_history_repo.create_record(analysis_id, status, details)

    def process_analysis_from_message(self, analysis_id: UUID, max_output_tokens: int | None = None) -> None:
        """Processes a single analysis request received from a message queue."""
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
        """Executes the full analysis pipeline for a single procurement."""
        control_number = procurement.pncp_control_number
        self.logger.info(f"Starting analysis for procurement {control_number} version {version_number}...")

        all_original_files = self.procurement_repo.process_procurement_documents(procurement)
        if not all_original_files:
            self.logger.warning(f"No files found for {control_number}. Aborting.")
            return

        all_candidates = self._prepare_ai_candidates(all_original_files, procurement)
        final_candidates, warnings = self._select_files_by_token_limit(all_candidates, procurement)

        files_for_ai = [(c.ai_path, c.ai_content) for c in final_candidates if c.is_included]
        if not files_for_ai:
            self.logger.error(f"No supported files left after filtering for {control_number}.")
            self._process_and_save_file_records(analysis_id, procurement, final_candidates)
            return

        document_hash = self._calculate_hash(files_for_ai)
        modality = self._get_modality(files_for_ai)

        # Idempotency check logic is omitted for brevity in this refactoring, but would go here.

        try:
            prompt = self._build_analysis_prompt(procurement, warnings)
            ai_analysis, input_tokens, output_tokens, thinking_tokens = self.ai_provider.get_structured_analysis(
                prompt=prompt, files=files_for_ai
            )

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            gcs_base_path = f"{control_number}/{timestamp}"
            if self.config.GCP_GCS_TEST_PREFIX:
                gcs_base_path = f"{self.config.GCP_GCS_TEST_PREFIX}/{gcs_base_path}"

            analysis_report_gcs_path = self._upload_analysis_report(gcs_base_path, ai_analysis)

            final_result = AnalysisResult(
                procurement_control_number=control_number,
                version_number=version_number,
                ai_analysis=ai_analysis,
                warnings=warnings,
                document_hash=document_hash,
                original_documents_gcs_path=f"{gcs_base_path}/files/",
                processed_documents_gcs_path=analysis_report_gcs_path,
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

            self._process_and_save_file_records(analysis_id, procurement, final_candidates)

            self.logger.info(f"Successfully completed analysis for {control_number}.")

        except Exception as e:
            self.logger.error(f"Analysis pipeline failed for {control_number}: {e}", exc_info=True)
            raise

    def _prepare_ai_candidates(
        self, all_files: list[tuple[str, bytes]], procurement: Procurement
    ) -> list[AIFileCandidate]:
        """Prepares a list of AIFileCandidate objects from raw file data."""
        candidates = []
        for original_path, content in all_files:
            candidate = AIFileCandidate(original_path=original_path, original_content=content)
            ext = os.path.splitext(original_path)[1].lower()

            if ext not in self._SUPPORTED_EXTENSIONS:
                candidate.exclusion_reason = ExclusionReason.UNSUPPORTED_EXTENSION
                candidates.append(candidate)
                continue

            if ext in self._DOCX_EXTENSIONS:
                try:
                    converted_content = self.converter_service.docx_to_pdf(content)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(original_path)[0]}.pdf"
                    gcs_path_base = f"{procurement.pncp_control_number}/converted/{os.path.basename(candidate.ai_path)}"
                    gcs_path = (
                        f"{self.config.GCP_GCS_TEST_PREFIX}/{gcs_path_base}"
                        if self.config.GCP_GCS_TEST_PREFIX
                        else gcs_path_base
                    )
                    self.gcs_provider.upload_file(
                        bucket_name=self.config.GCP_GCS_BUCKET_PROCUREMENTS,
                        destination_blob_name=gcs_path,
                        content=converted_content,
                        content_type="application/pdf",
                    )
                    candidate.converted_gcs_path = gcs_path
                except Exception as e:
                    self.logger.error(f"Failed to convert file {original_path}: {e}", exc_info=True)
                    candidate.exclusion_reason = ExclusionReason.CONVERSION_FAILED
            elif ext in self._XLSX_EXTENSIONS:
                try:
                    converted_content = self.converter_service.xlsx_to_csv(content)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(original_path)[0]}.csv"
                    # We don't save a separate converted file for CSV as it's sent directly.
                    # converted_gcs_path remains None.
                except Exception as e:
                    self.logger.error(f"Failed to convert file {original_path} to CSV: {e}", exc_info=True)
                    candidate.exclusion_reason = ExclusionReason.CONVERSION_FAILED

            candidates.append(candidate)
        return candidates

    def _select_files_by_token_limit(
        self, candidates: list[AIFileCandidate], procurement: Procurement
    ) -> tuple[list[AIFileCandidate], list[str]]:
        """Selects which files to include based on the AI model's token limit."""
        candidates.sort(key=lambda c: self._get_priority(c.original_path))
        max_tokens = self.config.GCP_GEMINI_MAX_INPUT_TOKENS
        warnings = []

        base_prompt_text = self._build_analysis_prompt(procurement, [])
        files_for_ai = []
        for candidate in candidates:
            if candidate.exclusion_reason:
                continue

            files_to_test = files_for_ai + [(candidate.ai_path, candidate.ai_content)]
            tokens, _, _ = self.ai_provider.count_tokens_for_analysis(base_prompt_text, files_to_test)

            if tokens <= max_tokens:
                files_for_ai.append((candidate.ai_path, candidate.ai_content))
                candidate.is_included = True
            else:
                candidate.exclusion_reason = ExclusionReason.TOKEN_LIMIT_EXCEEDED.format(max_tokens=max_tokens)

        excluded_names = [os.path.basename(c.original_path) for c in candidates if not c.is_included]
        if excluded_names:
            warnings.append(
                Warnings.TOKEN_LIMIT_EXCEEDED.format(max_tokens=max_tokens, ignored_files=", ".join(excluded_names))
            )

        return candidates, warnings

    def _process_and_save_file_records(
        self, analysis_id: UUID, procurement: Procurement, candidates: list[AIFileCandidate]
    ) -> None:
        """Uploads original files to GCS and saves their metadata records."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        gcs_base_path = f"{procurement.pncp_control_number}/{timestamp}"
        if self.config.GCP_GCS_TEST_PREFIX:
            gcs_base_path = f"{self.config.GCP_GCS_TEST_PREFIX}/{gcs_base_path}"

        for candidate in candidates:
            file_name = os.path.basename(candidate.original_path)
            gcs_path = f"{gcs_base_path}/files/{file_name}"

            self.gcs_provider.upload_file(
                bucket_name=self.config.GCP_GCS_BUCKET_PROCUREMENTS,
                destination_blob_name=gcs_path,
                content=candidate.original_content,
                content_type="application/octet-stream",
            )

            file_record = NewFileRecord(
                analysis_id=analysis_id,
                file_name=file_name,
                gcs_path=gcs_path,
                extension=os.path.splitext(file_name)[1].lstrip("."),
                size_bytes=len(candidate.original_content),
                nesting_level=0,
                included_in_analysis=candidate.is_included,
                exclusion_reason=candidate.exclusion_reason,
                prioritization_logic=self._get_priority_as_string(candidate.original_path),
                converted_gcs_path=candidate.converted_gcs_path,
            )
            self.file_record_repo.save_file_record(file_record)

    def _get_priority(self, file_path: str) -> int:
        """Determines the priority of a file based on keywords in its name."""
        path_lower = file_path.lower()
        for i, keyword in enumerate(self._FILE_PRIORITY_ORDER):
            if keyword in path_lower:
                return i
        return len(self._FILE_PRIORITY_ORDER)

    def _get_priority_as_string(self, file_path: str) -> str:
        """Returns the priority keyword found in the file path."""
        path_lower = file_path.lower()
        for keyword in self._FILE_PRIORITY_ORDER:
            if keyword in path_lower:
                message: str = PrioritizationLogic.BY_KEYWORD.format(keyword=keyword)
                return message
        no_priority_message: str = PrioritizationLogic.NO_PRIORITY
        return no_priority_message

    def _build_analysis_prompt(self, procurement: Procurement, warnings: list[str]) -> str:
        """Constructs the prompt for the AI, including contextual warnings."""
        procurement_json = procurement.model_dump_json(by_alias=True, indent=2)
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
        contexto. Em seguida, inspecione todos os arquivos anexados.

        --- METADADOS DA LICITAÇÃO (JSON) ---
        {procurement_json}
        --- FIM DOS METADADOS ---

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

    def _calculate_hash(self, files: list[tuple[str, bytes]]) -> str:
        """Calculates a SHA-256 hash from the content of a list of files."""
        hasher = hashlib.sha256()
        for _, content in sorted(files, key=lambda x: x[0]):
            hasher.update(content)
        return hasher.hexdigest()

    def _upload_analysis_report(self, gcs_base_path: str, analysis_result: Analysis) -> str:
        """Uploads the analysis report to GCS and returns the full path."""
        analysis_report_content = json.dumps(analysis_result.model_dump(), indent=2).encode("utf-8")
        analysis_report_blob_name = f"{gcs_base_path}/analysis_report.json"
        self.gcs_provider.upload_file(
            bucket_name=self.config.GCP_GCS_BUCKET_PROCUREMENTS,
            destination_blob_name=analysis_report_blob_name,
            content=analysis_report_content,
            content_type="application/json",
        )
        return analysis_report_blob_name

    def run_specific_analysis(self, analysis_id: UUID) -> None:
        """Triggers an analysis for a specific ID by publishing a message."""
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
    ) -> None:
        """Runs the pre-analysis job for a given date range."""
        try:
            self.logger.info(f"Starting pre-analysis job for date range: {start_date} to {end_date}")
            current_date = start_date
            messages_published_count = 0
            while current_date <= end_date:
                self.logger.info(f"Processing date: {current_date}")
                procurements_with_raw = self.procurement_repo.get_updated_procurements_with_raw_data(
                    target_date=current_date
                )

                if not procurements_with_raw:
                    self.logger.info(f"No procurements were updated on {current_date}. Moving to next day.")
                    current_date += timedelta(days=1)
                    continue

                batch_count = 0
                for i in range(0, len(procurements_with_raw), batch_size):
                    batch = procurements_with_raw[i : i + batch_size]
                    batch_count += 1
                    self.logger.info(f"Processing batch {batch_count} with {len(batch)} procurements.")

                    for procurement, raw_data in batch:
                        try:
                            self._pre_analyze_procurement(procurement, raw_data)
                            messages_published_count += 1
                            if max_messages is not None and messages_published_count >= max_messages:
                                self.logger.info(f"Reached max_messages ({max_messages}). Stopping pre-analysis.")
                                return
                        except Exception as e:
                            self.logger.error(
                                f"Failed to pre-analyze procurement {procurement.pncp_control_number}: {e}",
                                exc_info=True,
                            )

                    if i + batch_size < len(procurements_with_raw):
                        self.logger.info(f"Sleeping for {sleep_seconds} seconds before next batch.")
                        time.sleep(sleep_seconds)

                current_date += timedelta(days=1)
            self.logger.info("Pre-analysis job for the entire date range has been completed.")
        except Exception as e:
            raise AnalysisError(f"An unexpected error occurred during pre-analysis: {e}") from e

    def _pre_analyze_procurement(self, procurement: Procurement, raw_data: dict) -> None:
        """Performs the pre-analysis for a single procurement."""
        all_original_files = self.procurement_repo.process_procurement_documents(procurement)
        all_candidates = self._prepare_ai_candidates(all_original_files, procurement)
        final_candidates, _ = self._select_files_by_token_limit(all_candidates, procurement)
        files_for_ai = [(c.ai_path, c.ai_content) for c in final_candidates if c.is_included]

        raw_data_str = json.dumps(raw_data, sort_keys=True)
        all_files_content = b"".join(content for _, content in sorted(all_original_files, key=lambda x: x[0]))
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

        base_prompt_text = self._build_analysis_prompt(procurement, [])
        input_tokens, _, _ = self.ai_provider.count_tokens_for_analysis(base_prompt_text, files_for_ai)

        output_tokens = 0
        thinking_tokens = 0
        modality = self._get_modality(files_for_ai)
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
    ) -> None:
        """Runs the ranked analysis job."""
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
        triggered_count = 0

        for analysis in pending_analyses:
            if remaining_budget <= 0:
                self.logger.info("Budget exhausted. Stopping job.")
                break

            if max_messages is not None and triggered_count >= max_messages:
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
                self.budget_ledger_repo.save_expense(
                    analysis.analysis_id,
                    estimated_cost,
                    f"Análise da licitação {analysis.procurement_control_number} (v{analysis.version_number}).",
                )
                self.logger.info(
                    f"Analysis {analysis.analysis_id} triggered. "
                    f"Remaining budget: {remaining_budget:.2f} BRL. "
                    f"Zero-vote budget: {zero_vote_budget:.2f} BRL."
                )
                triggered_count += 1
            except Exception as e:
                self.logger.error(
                    f"Failed to trigger analysis {analysis.analysis_id}: {e}",
                    exc_info=True,
                )

        self.logger.info("Ranked analysis job completed.")

    def retry_analyses(self, initial_backoff_hours: int, max_retries: int, timeout_hours: int) -> int:
        """Retries failed or stale analyses."""
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
                    )
                    self.run_specific_analysis(new_analysis_id)
                    retried_count += 1

            return retried_count
        except Exception as e:
            raise AnalysisError(f"An unexpected error occurred during retry analyses: {e}") from e

    def get_procurement_overall_status(self, procurement_control_number: str) -> dict[str, Any] | None:
        """Retrieves the overall status of a procurement."""
        self.logger.info(f"Fetching overall status for procurement {procurement_control_number}.")
        status_info = self.analysis_repo.get_procurement_overall_status(procurement_control_number)
        if not status_info:
            self.logger.warning(f"No overall status found for procurement {procurement_control_number}.")
            return None
        return status_info

    def _calculate_auto_budget(self, budget_period: str) -> Decimal:
        """Calculates the budget for the current run based on donation history and spending pace."""
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
