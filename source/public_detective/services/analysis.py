"""This module defines the core service for handling procurement analyses."""

import hashlib
import json
import os
import time
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
from public_detective.services.pricing_service import Modality, PricingService


class AnalysisService:
    """Orchestrates the entire procurement analysis pipeline.

    This service is the central component responsible for coordinating all the
    steps involved in analyzing a public procurement. It fetches procurement
    documents, prepares them for AI analysis by applying business rules,
    invokes the AI model, and persists all results and metadata to the
    database and Google Cloud Storage.
    """

    procurement_repo: ProcurementsRepository
    analysis_repo: AnalysisRepository
    file_record_repo: FileRecordsRepository
    status_history_repo: StatusHistoryRepository
    budget_ledger_repo: BudgetLedgerRepository
    ai_provider: AiProvider
    gcs_provider: GcsProvider
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
    _MAX_SIZE_BYTES_FOR_AI = 20 * 1024 * 1024

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
        """Initializes the service with its dependencies.

        Args:
            procurement_repo: The repository for procurement data.
            analysis_repo: The repository for analysis data.
            file_record_repo: The repository for file record data.
            status_history_repo: The repository for status history data.
            budget_ledger_repo: The repository for budget ledger data.
            ai_provider: The provider for AI services.
            gcs_provider: The provider for Google Cloud Storage services.
            pubsub_provider: The provider for Pub/Sub services.
        """
        self.procurement_repo = procurement_repo
        self.analysis_repo = analysis_repo
        self.file_record_repo = file_record_repo
        self.status_history_repo = status_history_repo
        self.budget_ledger_repo = budget_ledger_repo
        self.ai_provider = ai_provider
        self.gcs_provider = gcs_provider
        self.pubsub_provider = pubsub_provider
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()
        self.pricing_service = PricingService()

    def _get_modality(self, files: list[tuple[str, bytes]]) -> Modality:
        """Determines the modality of an analysis based on file extensions.

        The modality is determined by the first file with a non-text modality.
        If no non-text files are found, the modality is TEXT.

        Args:
            files: A list of tuples, where each tuple contains the file path
                and its content.

        Returns:
            The determined modality.
        """
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
        """Updates the analysis status and records the change in the history table.

        Args:
            analysis_id: The ID of the analysis to update.
            status: The new status to set for the analysis.
            details: Optional details about the status change.
        """
        self.analysis_repo.update_analysis_status(analysis_id, status)
        self.status_history_repo.create_record(analysis_id, status, details)

    def process_analysis_from_message(self, analysis_id: UUID, max_output_tokens: int | None = None) -> None:
        """Processes a single analysis request received from a message queue.

        This method is typically called by a worker that is consuming messages
        from a Pub/Sub subscription. It retrieves the analysis and associated
        procurement data, then orchestrates the full analysis pipeline.

        Args:
            analysis_id: The unique ID of the analysis to be processed.
            max_output_tokens: An optional token limit for the AI analysis.

        Raises:
            AnalysisError: If the analysis pipeline fails.
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

        This method performs the following steps:
        1.  Fetches all document files associated with the procurement.
        2.  Applies business rules to select a subset of files for AI analysis.
        3.  Calculates a hash of the selected files to check for idempotency.
        4.  If a previous analysis with the same hash exists, it aborts.
        5.  Invokes the AI provider to get a structured analysis of the files.
        6.  Saves the analysis result to the `procurement_analyses` table.
        7.  Saves a detailed record for each original file to the `file_records`
            table, including its GCS path and analysis inclusion status.

        Args:
            procurement: The procurement object to be analyzed.
            version_number: The version of the procurement being analyzed.
            analysis_id: The unique ID of the analysis to be processed.
            max_output_tokens: An optional token limit for the AI analysis.

        Raises:
            Exception: If the analysis pipeline fails.
        """
        control_number = procurement.pncp_control_number
        self.logger.info(f"Starting analysis for procurement {control_number} version {version_number}...")

        all_original_files = self.procurement_repo.process_procurement_documents(procurement)

        if not all_original_files:
            self.logger.warning(f"No files found for {control_number}. Aborting.")
            return

        files_for_ai, excluded_files, warnings, _ = self._select_and_prepare_files_for_ai(
            all_original_files, procurement
        )

        if not files_for_ai:
            self.logger.error(f"No supported files left after filtering for {control_number}.")
            return

        document_hash = self._calculate_hash(files_for_ai)
        existing_analysis = self.analysis_repo.get_analysis_by_hash(document_hash)
        modality = self._get_modality(files_for_ai)

        if existing_analysis:
            self.logger.info(f"Found existing analysis with hash {document_hash}. Reusing results.")
            # Create the GCS paths based on the new analysis timestamp
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            gcs_base_path = f"{control_number}/{timestamp}"
            if self.config.GCP_GCS_TEST_PREFIX:
                gcs_base_path = f"{self.config.GCP_GCS_TEST_PREFIX}/{gcs_base_path}"

            # Copy results from the existing analysis
            reused_result = AnalysisResult(
                procurement_control_number=control_number,
                version_number=version_number,
                ai_analysis=Analysis(
                    risk_score=existing_analysis.ai_analysis.risk_score,
                    risk_score_rationale=existing_analysis.ai_analysis.risk_score_rationale,
                    procurement_summary=existing_analysis.ai_analysis.procurement_summary,
                    analysis_summary=existing_analysis.ai_analysis.analysis_summary,
                    red_flags=existing_analysis.ai_analysis.red_flags,
                    seo_keywords=existing_analysis.ai_analysis.seo_keywords,
                ),
                warnings=existing_analysis.warnings,
                document_hash=document_hash,
                original_documents_gcs_path=f"{gcs_base_path}/files/",
                processed_documents_gcs_path=f"{gcs_base_path}/analysis_report.json",
            )
            input_cost, output_cost, thinking_cost, total_cost = self.pricing_service.calculate(
                existing_analysis.input_tokens_used,
                existing_analysis.output_tokens_used,
                existing_analysis.thinking_tokens_used,
                modality=modality,
            )
            self.analysis_repo.save_analysis(
                analysis_id=analysis_id,
                result=reused_result,
                input_tokens=existing_analysis.input_tokens_used,
                output_tokens=existing_analysis.output_tokens_used,
                thinking_tokens=existing_analysis.thinking_tokens_used,
                input_cost=input_cost,
                output_cost=output_cost,
                thinking_cost=thinking_cost,
                total_cost=total_cost,
            )

            # Even if we reuse the analysis, we must record the files for the *new* analysis run
            self._process_and_save_file_records(
                analysis_id=analysis_id,
                gcs_base_path=gcs_base_path,
                all_files=all_original_files,
                included_files=files_for_ai,
                excluded_files=excluded_files,
            )
            self.logger.info(f"Successfully reused analysis for {control_number}.")
            return

        try:
            prompt = self._build_analysis_prompt(procurement, warnings)
            ai_analysis, input_tokens, output_tokens, thinking_tokens = self.ai_provider.get_structured_analysis(
                prompt=prompt,
                files=files_for_ai,
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

            self._process_and_save_file_records(
                analysis_id=analysis_id,
                gcs_base_path=gcs_base_path,
                all_files=all_original_files,
                included_files=files_for_ai,
                excluded_files=excluded_files,
            )

            self.logger.info(f"Successfully completed analysis for {control_number}.")

        except Exception as e:
            self.logger.error(f"Analysis pipeline failed for {control_number}: {e}", exc_info=True)
            raise

    def _calculate_hash(self, files: list[tuple[str, bytes]]) -> str:
        """Calculates a SHA-256 hash from the content of a list of files.

        Args:
            files: A list of tuples, where each tuple contains the file path and its content.

        Returns:
            The calculated SHA-256 hash.
        """
        hasher = hashlib.sha256()
        for _, content in sorted(files, key=lambda x: x[0]):
            hasher.update(content)
        return hasher.hexdigest()

    def _upload_analysis_report(self, gcs_base_path: str, analysis_result: Analysis) -> str:
        """Uploads the analysis report to GCS and returns the full path.

        Args:
            gcs_base_path: The base GCS path for this analysis run.
            analysis_result: The analysis result to be uploaded.

        Returns:
            The full GCS path of the uploaded analysis report.
        """
        analysis_report_content = json.dumps(analysis_result.model_dump(), indent=2).encode("utf-8")
        analysis_report_blob_name = f"{gcs_base_path}/analysis_report.json"
        self.gcs_provider.upload_file(
            bucket_name=self.config.GCP_GCS_BUCKET_PROCUREMENTS,
            destination_blob_name=analysis_report_blob_name,
            content=analysis_report_content,
            content_type="application/json",
        )
        return analysis_report_blob_name

    def _process_and_save_file_records(
        self,
        analysis_id: UUID,
        gcs_base_path: str,
        all_files: list[tuple[str, bytes]],
        included_files: list[tuple[str, bytes]],
        excluded_files: dict[str, str],
    ) -> None:
        """Uploads every original file to GCS and saves its metadata record.

        This method saves the metadata record to the database.
        For each file, it determines if it was included in the AI analysis and
        records the reason for any exclusion.

        Args:
            analysis_id: The ID of the parent analysis run.
            gcs_base_path: The base GCS path for this analysis run.
            all_files: A list of all original files (path, content).
            included_files: The list of files that were sent to the AI.
            excluded_files: A dictionary mapping excluded file paths to their
                exclusion reason.
        """
        included_filenames = {f[0] for f in included_files}

        for file_path, file_content in all_files:
            file_name = os.path.basename(file_path)
            gcs_path = f"{gcs_base_path}/files/{file_name}"

            self.gcs_provider.upload_file(
                bucket_name=self.config.GCP_GCS_BUCKET_PROCUREMENTS,
                destination_blob_name=gcs_path,
                content=file_content,
                content_type="application/octet-stream",
            )

            is_included = file_path in included_filenames
            exclusion_reason = excluded_files.get(file_path)

            file_record = NewFileRecord(
                analysis_id=analysis_id,
                file_name=file_name,
                gcs_path=gcs_path,
                extension=os.path.splitext(file_name)[1].lstrip("."),
                size_bytes=len(file_content),
                nesting_level=0,
                included_in_analysis=is_included,
                exclusion_reason=exclusion_reason,
                prioritization_logic=self._get_priority_as_string(file_path),
            )
            self.file_record_repo.save_file_record(file_record)

    def _select_and_prepare_files_for_ai(
        self, all_files: list[tuple[str, bytes]], procurement: Procurement
    ) -> tuple[list[tuple[str, bytes]], dict[str, str], list[str], int]:
        """Applies business rules to filter and prioritize files for AI analysis.

        This method implements a dynamic file selection logic based on the AI
        model's token limit. It prioritizes files and adds them to the analysis
        until the total token count approaches the maximum allowed, ensuring
        optimal use of the context window.

        Args:
            all_files: A list of all available files for the procurement.
            procurement: The procurement object, used to build the base prompt.

        Returns:
            A tuple containing:
            - A list of the selected files (path, content) to be sent to the AI.
            - A dictionary mapping the path of each excluded file to the reason
              for its exclusion.
            - A list of warning messages to be included in the AI prompt.
            - The total calculated input tokens for the final selection.
        """
        excluded_files: dict[str, str] = {}
        max_tokens = self.config.GCP_GEMINI_MAX_INPUT_TOKENS

        # 1. Initial filtering by extension and size
        candidate_files = []
        max_size_mb = self._MAX_SIZE_BYTES_FOR_AI / 1024 / 1024
        for path, content in all_files:
            if not path.lower().endswith(self._SUPPORTED_EXTENSIONS):
                excluded_files[path] = ExclusionReason.UNSUPPORTED_EXTENSION
            elif len(content) > self._MAX_SIZE_BYTES_FOR_AI:
                excluded_files[path] = ExclusionReason.TOTAL_SIZE_LIMIT_EXCEEDED.format(max_size_mb=max_size_mb)
            else:
                candidate_files.append((path, content))

        # 2. Sort candidates by priority
        candidate_files.sort(key=lambda item: self._get_priority(item[0]))

        # 3. Dynamic selection based on tokens
        final_files: list[tuple[str, bytes]] = []
        excluded_candidates = candidate_files.copy()

        # Helper to generate warning message and count its token cost
        def get_warning_info(ignored_files: list[tuple[str, bytes]]) -> tuple[str, int]:
            if not ignored_files:
                return "", 0

            ignored_names = ", ".join([os.path.basename(p) for p, _ in ignored_files])
            warning_str = Warnings.TOKEN_LIMIT_EXCEEDED.format(max_tokens=max_tokens, ignored_files=ignored_names)

            # The cost is the warning itself plus the prompt structure that holds it
            prompt_with_warning = self._build_analysis_prompt(procurement, [warning_str])
            prompt_tokens, _, _ = self.ai_provider.count_tokens_for_analysis(prompt_with_warning, [])
            return warning_str, prompt_tokens

        # Calculate base prompt tokens (no files, no warnings)
        base_prompt_text = self._build_analysis_prompt(procurement, [])
        current_token_count, _, _ = self.ai_provider.count_tokens_for_analysis(base_prompt_text, [])

        # Check if the prompt with a warning about all files already exceeds the limit
        initial_warning_str, tokens_with_initial_warning = get_warning_info(excluded_candidates)
        if tokens_with_initial_warning > max_tokens:
            self.logger.warning(f"Base prompt with all files excluded already exceeds token limit for {procurement.pncp_control_number}")
            for path, _ in candidate_files:
                excluded_files[path] = ExclusionReason.TOKEN_LIMIT_EXCEEDED.format(max_tokens=max_tokens)
            return [], excluded_files, [initial_warning_str], tokens_with_initial_warning

        current_token_count = tokens_with_initial_warning

        # Iteratively try to move files from excluded to final
        for i in range(len(candidate_files)):
            candidate_to_add = candidate_files[i]
            path, _ = candidate_to_add

            # Calculate tokens for the file itself
            file_tokens, _, _ = self.ai_provider.count_tokens_for_analysis("", [candidate_to_add])

            # Calculate how many tokens we save by removing this file from the warning
            temp_excluded_list = [f for f in excluded_candidates if f != candidate_to_add]
            _, tokens_with_new_warning = get_warning_info(temp_excluded_list)

            # The warning cost difference is not linear, so we calculate the full new prompt
            # The new total would be: base_prompt + new_warning + final_files + candidate_file
            prompt_with_new_warning = self._build_analysis_prompt(procurement, ([get_warning_info(temp_excluded_list)[0]] if temp_excluded_list else []))
            potential_total, _, _ = self.ai_provider.count_tokens_for_analysis(prompt_with_new_warning, final_files + [candidate_to_add])


            if potential_total <= max_tokens:
                final_files.append(candidate_to_add)
                excluded_candidates.remove(candidate_to_add)
                current_token_count = potential_total
            else:
                excluded_files[path] = ExclusionReason.TOKEN_LIMIT_EXCEEDED.format(max_tokens=max_tokens)

        # Finalize warnings and token count
        final_warning_str, final_token_count = get_warning_info(excluded_candidates)
        final_prompt = self._build_analysis_prompt(procurement, [final_warning_str] if final_warning_str else [])
        final_token_count, _, _ = self.ai_provider.count_tokens_for_analysis(final_prompt, final_files)

        final_warnings = [final_warning_str] if final_warning_str else []
        for msg in final_warnings:
            if msg:
                self.logger.warning(msg)

        return final_files, excluded_files, final_warnings, final_token_count

    def _get_priority(self, file_path: str) -> int:
        """Determines the priority of a file based on keywords in its name.

        Args:
            file_path: The path of the file to be prioritized.

        Returns:
            The priority of the file, where a lower number indicates a higher priority.
        """
        path_lower = file_path.lower()
        for i, keyword in enumerate(self._FILE_PRIORITY_ORDER):
            if keyword in path_lower:
                return i
        return len(self._FILE_PRIORITY_ORDER)

    def _get_priority_as_string(self, file_path: str) -> str:
        """Returns the priority keyword found in the file path.

        Args:
            file_path: The path of the file to be analyzed.

        Returns:
            The priority keyword found in the file path, or a default message if no keyword is found.
        """
        path_lower = file_path.lower()
        for keyword in self._FILE_PRIORITY_ORDER:
            if keyword in path_lower:
                message: str = PrioritizationLogic.BY_KEYWORD.format(keyword=keyword)
                return message
        no_priority_message: str = PrioritizationLogic.NO_PRIORITY
        return no_priority_message

    def _build_analysis_prompt(self, procurement: Procurement, warnings: list[str]) -> str:
        """Constructs the prompt for the AI, including contextual warnings.

        Args:
            procurement: The procurement object to be analyzed.
            warnings: A list of warnings to be included in the prompt.

        Returns:
            The constructed prompt for the AI.
        """
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

    def run_specific_analysis(self, analysis_id: UUID) -> None:
        """Triggers an analysis for a specific ID by publishing a message.

        This method is intended to be called by a user-facing interface (like
        a CLI). It finds a 'PENDING_ANALYSIS' record and publishes a message
        to the procurement topic, which will be picked up by a worker to
        execute the actual analysis.

        Args:
            analysis_id: The ID of the analysis to be triggered.

        Raises:
            AnalysisError: If an unexpected error occurs during the process.
            ValueError: If the Pub/Sub provider has not been configured.
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
    ) -> None:
        """Runs the pre-analysis job for a given date range.

        This method scans for new procurements within the specified date
        range, processes them in batches, and creates 'PENDING_ANALYSIS'
        records for each new, unique procurement.

        Args:
            start_date: The start date of the range to scan.
            end_date: The end date of the range to scan.
            batch_size: The number of procurements to process in each batch.
            sleep_seconds: The time to sleep between batches to avoid API
                rate limiting.
            max_messages: An optional limit on the number of pre-analysis
                tasks to create.

        Raises:
            AnalysisError: If an unexpected error occurs during the pre-analysis process.
        """
        try:
            self.logger.info(f"Starting pre-analysis job for date range: {start_date} to {end_date}")
            current_date = start_date
            messages_published_count = 0  # Initialize counter
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
                            messages_published_count += 1  # Increment count on successful pre-analysis
                            if max_messages is not None and messages_published_count >= max_messages:
                                self.logger.info(f"Reached max_messages ({max_messages}). Stopping pre-analysis.")
                                return  # Exit the function
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
        """Performs the pre-analysis for a single procurement.

        This involves:
        1.  Processing documents to get a list of files for AI analysis.
        2.  Calculating a hash of the procurement's content to check for
            idempotency against existing versions.
        3.  If it's a new version, saving it to the database.
        4.  Creating a new 'PENDING_ANALYSIS' record.

        Args:
            procurement: The procurement to be pre-analyzed.
            raw_data: The raw JSON data of the procurement.
        """
        all_original_files = self.procurement_repo.process_procurement_documents(procurement)
        files_for_ai, _, _, input_tokens = self._select_and_prepare_files_for_ai(all_original_files, procurement)

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
        """Runs the ranked analysis job.

        This method fetches all pending analyses, calculates their estimated
        cost, and triggers them in ranked order until the specified or calculated
        provided budget is exhausted or the message limit is reached.

        Args:
            use_auto_budget: Flag to determine if automatic budget calculation should be used.
            budget_period: The period for auto-budget calculation ('daily', 'weekly', 'monthly').
            zero_vote_budget_percent: The percentage of the budget to be used for procurements with zero votes.
            budget: The manual budget for the analysis run.
            max_messages: An optional limit on the number of analyses to trigger.
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
        """Retries failed or stale analyses.

        This method identifies analyses that have failed or have been in
        progress for too long, and triggers a new analysis for them,
        respecting an exponential backoff strategy.

        Args:
            initial_backoff_hours: The base duration to wait before the first
                retry.
            max_retries: The maximum number of times an analysis will be
                retried.
            timeout_hours: The number of hours after which an 'IN_PROGRESS'
                task is considered stale.

        Returns:
            The number of analyses that were successfully triggered for retry.

        Raises:
            AnalysisError: If an unexpected error occurs during the process.
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
                    # Modality for retries is not available, so we assume TEXT
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
        """Retrieves the overall status of a procurement.

        This method queries the database to get a consolidated view of the
        latest analysis status for a given procurement, including its risk
        score and the date of the last update.

        Args:
            procurement_control_number: The unique control number of the
                procurement.

        Returns:
            A dictionary containing the overall status information, or None if
            no analysis is found for the given procurement.
        """
        self.logger.info(f"Fetching overall status for procurement {procurement_control_number}.")
        status_info = self.analysis_repo.get_procurement_overall_status(procurement_control_number)
        if not status_info:
            self.logger.warning(f"No overall status found for procurement {procurement_control_number}.")
            return None
        return status_info  # type: ignore

    def _calculate_auto_budget(self, budget_period: str) -> Decimal:
        """Calculates the budget for the current run based on donation history and spending pace.

        Args:
            budget_period: The period for auto-budget calculation ('daily', 'weekly', 'monthly').

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
