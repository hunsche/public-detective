import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from models.analyses import Analysis, AnalysisResult
from models.file_records import NewFileRecord
from models.procurement_analysis_status import ProcurementAnalysisStatus
from models.procurements import Procurement
from providers.ai import AiProvider
from providers.config import Config, ConfigProvider
from providers.gcs import GcsProvider
from providers.logging import Logger, LoggingProvider
from providers.pubsub import PubSubProvider
from repositories.analyses import AnalysisRepository
from repositories.file_records import FileRecordsRepository
from repositories.procurements import ProcurementsRepository
from repositories.status_history import StatusHistoryRepository
from constants.analysis_feedback import ExclusionReason, PrioritizationLogic, Warnings


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
    ai_provider: AiProvider
    gcs_provider: GcsProvider
    pubsub_provider: PubSubProvider | None
    logger: Logger
    config: Config

    _SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".doc", ".rtf", ".xlsx", ".xls", ".csv")
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
    _MAX_FILES_FOR_AI = 10
    _MAX_SIZE_BYTES_FOR_AI = 20 * 1024 * 1024

    def __init__(
        self,
        procurement_repo: ProcurementsRepository,
        analysis_repo: AnalysisRepository,
        file_record_repo: FileRecordsRepository,
        status_history_repo: StatusHistoryRepository,
        ai_provider: AiProvider,
        gcs_provider: GcsProvider,
        pubsub_provider: PubSubProvider | None = None,
    ) -> None:
        """Initializes the service with its dependencies."""
        self.procurement_repo = procurement_repo
        self.analysis_repo = analysis_repo
        self.file_record_repo = file_record_repo
        self.status_history_repo = status_history_repo
        self.ai_provider = ai_provider
        self.gcs_provider = gcs_provider
        self.pubsub_provider = pubsub_provider
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()

    def _update_status_with_history(
        self, analysis_id: int, status: ProcurementAnalysisStatus, details: str | None = None
    ) -> None:
        """Updates the analysis status and records the change in the history table."""
        self.analysis_repo.update_analysis_status(analysis_id, status)
        self.status_history_repo.create_record(analysis_id, status, details)

    def process_analysis_from_message(self, analysis_id: int):
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
            self.analyze_procurement(procurement, analysis.version_number, analysis_id)
            self._update_status_with_history(
                analysis_id, ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL, "Analysis completed successfully."
            )
        except Exception as e:
            self.logger.error(f"Analysis pipeline failed for analysis {analysis_id}: {e}", exc_info=True)
            self._update_status_with_history(analysis_id, ProcurementAnalysisStatus.ANALYSIS_FAILED, str(e))
            raise

    def analyze_procurement(self, procurement: Procurement, version_number: int, analysis_id: int) -> None:
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
        """
        control_number = procurement.pncp_control_number
        self.logger.info(f"Starting analysis for procurement {control_number} version {version_number}...")

        all_original_files = self.procurement_repo.process_procurement_documents(procurement)

        if not all_original_files:
            self.logger.warning(f"No files found for {control_number}. Aborting.")
            return

        files_for_ai, excluded_files, warnings = self._select_and_prepare_files_for_ai(all_original_files)

        if not files_for_ai:
            self.logger.error(f"No supported files left after filtering for {control_number}.")
            return

        document_hash = self._calculate_hash(files_for_ai)
        existing_analysis = self.analysis_repo.get_analysis_by_hash(document_hash)

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
                    red_flags=existing_analysis.ai_analysis.red_flags,
                ),
                warnings=existing_analysis.warnings,
                document_hash=document_hash,
                original_documents_gcs_path=f"{gcs_base_path}/files/",
                processed_documents_gcs_path=f"{gcs_base_path}/analysis_report.json",
            )
            self.analysis_repo.save_analysis(analysis_id, reused_result)

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
            ai_analysis = self.ai_provider.get_structured_analysis(
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
            self.analysis_repo.save_analysis(analysis_id, final_result)

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

    def _process_and_save_file_records(
        self,
        analysis_id: int,
        gcs_base_path: str,
        all_files: list[tuple[str, bytes]],
        included_files: list[tuple[str, bytes]],
        excluded_files: dict[str, str],
    ) -> None:
        """Uploads every original file to GCS and saves its metadata record
        to the database.

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
        self,
        all_files: list[tuple[str, bytes]],
    ) -> tuple[list[tuple[str, bytes]], dict[str, str], list[str]]:
        """Applies business rules to filter and prioritize files for AI analysis.

        This method implements the core logic for deciding which files are
        most relevant for analysis, based on file type, keywords in the
        filename, and constraints on the number of files and total size.

        Args:
            all_files: A list of all available files for the procurement.

        Returns:
            A tuple containing:
            - A list of the selected files (path, content) to be sent to the AI.
            - A dictionary mapping the path of each excluded file to the reason
              for its exclusion.
            - A list of warning messages to be included in the AI prompt.
        """
        warnings = []
        excluded_files = {}

        # Filter by supported extensions
        supported_files, unsupported_files = [], []
        for path, content in all_files:
            if path.lower().endswith(self._SUPPORTED_EXTENSIONS):
                supported_files.append((path, content))
            else:
                unsupported_files.append(path)
        for path in unsupported_files:
            excluded_files[path] = ExclusionReason.UNSUPPORTED_EXTENSION

        # Sort by priority
        supported_files.sort(key=lambda item: self._get_priority(item[0]))

        # Filter by max number of files
        if len(supported_files) > self._MAX_FILES_FOR_AI:
            files_to_exclude = supported_files[self._MAX_FILES_FOR_AI :]
            for path, _ in files_to_exclude:
                excluded_files[path] = ExclusionReason.FILE_LIMIT_EXCEEDED.format(max_files=self._MAX_FILES_FOR_AI)

            warnings.append(
                Warnings.FILE_LIMIT_EXCEEDED.format(
                    max_files=self._MAX_FILES_FOR_AI,
                    ignored_files=", ".join(p for p, _ in files_to_exclude),
                )
            )
            selected_files = supported_files[: self._MAX_FILES_FOR_AI]
        else:
            selected_files = supported_files

        # Filter by size
        final_files = []
        current_size = 0
        files_excluded_by_size = []
        max_size_mb = self._MAX_SIZE_BYTES_FOR_AI / 1024 / 1024

        for path, content in selected_files:
            if current_size + len(content) > self._MAX_SIZE_BYTES_FOR_AI:
                excluded_files[path] = ExclusionReason.TOTAL_SIZE_LIMIT_EXCEEDED.format(max_size_mb=max_size_mb)
                files_excluded_by_size.append(path)
            else:
                final_files.append((path, content))
                current_size += len(content)

        if files_excluded_by_size:
            warnings.append(
                Warnings.TOTAL_SIZE_LIMIT_EXCEEDED.format(
                    max_size_mb=max_size_mb,
                    ignored_files=", ".join(files_excluded_by_size),
                )
            )

        for warning_msg in warnings:
            self.logger.warning(warning_msg)

        return final_files, excluded_files, warnings

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
                return PrioritizationLogic.BY_KEYWORD.format(keyword=keyword)
        return PrioritizationLogic.NO_PRIORITY

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
        fornecido, incluindo os campos `summary` e `risk_score_rationale`.

        Forneça um resumo conciso (em pt-br) de uma frase sobre os principais pontos e riscos da licitação.
        """

    def run_specific_analysis(self, analysis_id: int):
        """
        Runs the analysis for a specific analysis ID.
        """
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
            "analysis_id": analysis_id,
        }
        message_json = json.dumps(message_data)
        message_bytes = message_json.encode()
        self.pubsub_provider.publish(self.config.GCP_PUBSUB_TOPIC_PROCUREMENTS, message_bytes)
        self.logger.info(f"Published analysis request for analysis_id {analysis_id} to Pub/Sub.")

    def run_pre_analysis(
        self, start_date: date, end_date: date, batch_size: int, sleep_seconds: int, max_messages: int | None = None
    ):
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

    def _pre_analyze_procurement(self, procurement: Procurement, raw_data: dict):
        # 1. Get documents
        all_original_files = self.procurement_repo.process_procurement_documents(procurement)
        files_for_ai, _, warnings = self._select_and_prepare_files_for_ai(all_original_files)

        # 2. Calculate hash for procurement (raw data + all files)
        raw_data_str = json.dumps(raw_data, sort_keys=True)
        all_files_content = b"".join(content for _, content in sorted(all_original_files, key=lambda x: x[0]))
        procurement_content_hash = hashlib.sha256(raw_data_str.encode("utf-8") + all_files_content).hexdigest()

        # 3. Check for idempotency on procurement
        if self.procurement_repo.get_procurement_by_hash(procurement_content_hash):
            self.logger.info(f"Procurement with hash {procurement_content_hash} already exists. Skipping.")
            return

        # 4. Calculate hash for analysis (files for AI)
        analysis_document_hash = self._calculate_hash(files_for_ai)

        # 5. Get new version number
        latest_version = self.procurement_repo.get_latest_version(procurement.pncp_control_number)
        new_version = latest_version + 1

        # 6. Save new procurement version
        self.procurement_repo.save_procurement_version(
            procurement=procurement,
            raw_data=raw_data_str,
            version_number=new_version,
            content_hash=procurement_content_hash,
        )

        # 7. Count tokens
        prompt = self._build_analysis_prompt(procurement, warnings)
        token_count = self.ai_provider.count_tokens_for_analysis(prompt, files_for_ai)

        # 8. Calculate estimated cost
        estimated_cost = (token_count / 1000) * self.config.GCP_GEMINI_PRICE_PER_1K_TOKENS

        # 9. Save pre-analysis
        analysis_id = self.analysis_repo.save_pre_analysis(
            procurement_control_number=procurement.pncp_control_number,
            version_number=new_version,
            estimated_cost=estimated_cost,
            document_hash=analysis_document_hash,
        )
        self.status_history_repo.create_record(
            analysis_id, ProcurementAnalysisStatus.PENDING_ANALYSIS, "Pre-analysis completed."
        )

    def run_analysis(self, start_date: date, end_date: date):
        """
        Runs the Public Detective analysis job for the specified date range.
        """
        self.logger.info(f"Starting analysis job for date range: {start_date} to {end_date}")
        current_date = start_date
        while current_date <= end_date:
            self.logger.info(f"Processing date: {current_date}")
            updated_procurements = self.procurement_repo.get_updated_procurements(target_date=current_date)

            if not updated_procurements:
                self.logger.info(f"No procurements were updated on {current_date}. " "Moving to next day.")
                current_date += timedelta(days=1)
                continue

            self.logger.info(f"Found {len(updated_procurements)} updated procurements. " "Publishing to message queue.")
            success_count, failure_count = 0, 0
            for procurement in updated_procurements:
                published = self.procurement_repo.publish_procurement_to_pubsub(procurement)
                if published:
                    success_count += 1
                else:
                    failure_count += 1
            self.logger.info(
                f"Finished processing for {current_date}. Success: " f"{success_count}, Failures: {failure_count}"
            )
            current_date += timedelta(days=1)
        self.logger.info("Analysis job for the entire date range has been completed.")

    def reap_stale_analyses(self, timeout_minutes: int) -> int:
        """
        Resets the status of stale analyses to TIMEOUT and records the change.
        """
        stale_ids = self.analysis_repo.reset_stale_analyses(timeout_minutes)
        for analysis_id in stale_ids:
            self._update_status_with_history(
                analysis_id,
                ProcurementAnalysisStatus.TIMEOUT,
                f"Analysis timed out after {timeout_minutes} minutes.",
            )
        return len(stale_ids)

    def get_procurement_overall_status(self, procurement_control_number: str) -> dict[str, Any] | None:
        """
        Retrieves the overall status of a procurement.

        Args:
            procurement_control_number: The unique control number of the procurement.

        Returns:
            A dictionary with the overall status information or None if not found.
        """
        self.logger.info(f"Fetching overall status for procurement {procurement_control_number}.")
        status_info = self.analysis_repo.get_procurement_overall_status(procurement_control_number)
        if not status_info:
            self.logger.warning(f"No overall status found for procurement {procurement_control_number}.")
            return None
        return status_info  # type: ignore
