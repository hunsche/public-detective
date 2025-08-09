import json
import uuid
from datetime import date, timedelta
from typing import List, Tuple

import psycopg2
from models.analysis import Analysis, AnalysisResult
from models.procurement import Procurement
from providers.ai import AiProvider
from providers.gcs import GcsProvider
from providers.logging import Logger, LoggingProvider
from repositories.procurement import ProcurementRepository


class AnalysisService:
    """Service to orchestrate ETL jobs and the analysis of individual procurements.

    This class contains the core business logic for file filtering, prioritization,
    and the application of business rules (e.g., file count and size limits)
    before sending artifacts for AI analysis.
    """

    # --- Constants for Business Logic ---
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
    _MAX_SIZE_BYTES_FOR_AI = 20 * 1024 * 1024  # 20MB

    procurement_repo: ProcurementRepository
    logger: Logger
    ai_provider: AiProvider[Analysis]
    gcs_provider: GcsProvider

    def __init__(self) -> None:
        """Initializes the service and its dependencies."""
        self.procurement_repo = ProcurementRepository()
        self.logger = LoggingProvider().get_logger()
        self.ai_provider = AiProvider(Analysis)
        self.gcs_provider = GcsProvider()

    def analyze_procurement(self, procurement: Procurement) -> None:
        """Executes the full analysis pipeline for a single procurement."""
        control_number = procurement.pncp_control_number
        self.logger.info(f"Starting full analysis for procurement {control_number}...")

        file_records, all_final_files = (
            self.procurement_repo.process_procurement_documents(procurement)
        )

        if not file_records:
            self.logger.warning(
                f"No files found to process for {control_number}. Aborting."
            )
            return

        files_for_ai, warnings = self._select_and_prepare_files_for_ai(all_final_files)

        if not files_for_ai:
            self.logger.warning(
                f"No supported files left after filtering for {control_number}. Aborting AI analysis."
            )
            return

        master_zip_content = self.procurement_repo.create_zip_from_files(
            files_for_ai, control_number
        )
        if not master_zip_content:
            self.logger.error(
                f"Failed to create master ZIP for {control_number}. Aborting AI analysis."
            )
            return

        file_name_uuid = f"{uuid.uuid4()}.zip"

        try:
            prompt = self._build_analysis_prompt(procurement, warnings)
            analysis_result = self.ai_provider.get_structured_analysis(
                prompt=prompt,
                file_content=master_zip_content,
                file_display_name=f"{control_number.replace('/', '_')}.zip",
            )

            document_url = self._upload_document_to_gcs(
                master_zip_content, file_name_uuid
            )

            final_result = AnalysisResult(
                procurement_control_number=control_number,
                ai_analysis=analysis_result,
                gcs_document_url=document_url,
                warnings=warnings,
            )
            self._persist_ai_analysis(final_result)

        except Exception as e:
            self.logger.error(f"AI analysis pipeline failed for {control_number}: {e}")
            raise

    def _upload_document_to_gcs(self, zip_content: bytes, destination_name: str) -> str:
        """Uploads the aggregated ZIP content to Google Cloud Storage.

        This method uses the GcsProvider to handle the upload of the final
        ZIP archive, which contains the prioritized and filtered files for
        a given procurement. It assigns a unique, UUID-based name to the
        object in the storage bucket.

        Args:
            zip_content: The raw byte content of the master ZIP archive.
            destination_name: The unique filename (including the .zip extension)
                              for the object in the GCS bucket.

        Returns:
            The public URL of the uploaded file, which can be persisted for
            future reference and auditing.
        """
        bucket_name = self.gcs_provider.config.GCP_GCS_BUCKET_PROCUREMENTS
        return str(
            self.gcs_provider.upload_file(
                bucket_name=bucket_name,
                destination_blob_name=destination_name,
                content=zip_content,
                content_type="application/zip",
            )
        )

    def _select_and_prepare_files_for_ai(
        self, all_files: List[Tuple[str, bytes]]
    ) -> Tuple[List[Tuple[str, bytes]], List[str]]:
        """Applies business rules to filter, prioritize, and limit files for AI analysis."""
        warnings = []

        # Filter by supported extensions
        supported_files = [
            (path, content)
            for path, content in all_files
            if path.lower().endswith(self._SUPPORTED_EXTENSIONS)
        ]

        # Sort by priority
        def get_priority(file_path: str) -> int:
            path_lower = file_path.lower()
            for i, keyword in enumerate(self._FILE_PRIORITY_ORDER):
                if keyword in path_lower:
                    return i
            return len(self._FILE_PRIORITY_ORDER)

        supported_files.sort(key=lambda item: get_priority(item[0]))

        # Apply file count limit
        if len(supported_files) > self._MAX_FILES_FOR_AI:
            warning_msg = (
                f"File count limit exceeded. Found {len(supported_files)} supported files, "
                f"but only the top {self._MAX_FILES_FOR_AI} most important were included."
            )
            self.logger.warning(warning_msg)
            warnings.append(warning_msg)
            selected_files = supported_files[: self._MAX_FILES_FOR_AI]
        else:
            selected_files = supported_files

        # Apply total size limit
        final_files = []
        current_size = 0
        for path, content in selected_files:
            if current_size + len(content) > self._MAX_SIZE_BYTES_FOR_AI:
                warning_msg = (
                    f"Total size limit of {self._MAX_SIZE_BYTES_FOR_AI / 1024 / 1024:.1f}MB exceeded. "
                    "Some files were excluded from the analysis."
                )
                self.logger.warning(warning_msg)
                if warning_msg not in warnings:
                    warnings.append(warning_msg)
                break
            final_files.append((path, content))
            current_size += len(content)

        return final_files, warnings

    def _build_analysis_prompt(
        self, procurement: Procurement, warnings: List[str]
    ) -> str:
        """Constructs the prompt, including any warnings about excluded files."""
        procurement_json = procurement.model_dump_json(by_alias=True, indent=2)

        warnings_section = ""
        if warnings:
            warnings_text = "\n- ".join(warnings)
            warnings_section = f"""
            --- IMPORTANT WARNINGS ---
            The following issues were detected while preparing the files.
            Consider these limitations in your analysis:
            - {warnings_text}
            --- END OF WARNINGS ---
            """

        return f"""
        You are a senior auditor specializing in public procurement in Brazil.
        Your task is to analyze the documents contained within the attached ZIP
        archive to identify potential irregularities in the procurement process.
        {warnings_section}
        First, review the procurement's metadata in JSON format for context.
        Then, inspect all files inside the ZIP archive.

        --- PROCUREMENT METADATA (JSON) ---
        {procurement_json}
        --- END OF METADATA ---

        Based on all available information, analyze the bid for
        irregularities in the following categories. For each finding, you must
        extract the exact quote from one of the documents that supports your analysis.

        1.  Vendor-Specific Directing (DIRECTING)
        2.  Restriction of Competitiveness (COMPETITION_RESTRICTION)
        3.  Potential for Overpricing (OVERPRICE)

        Your response must be a JSON object that strictly adheres to the
        provided schema.
        """

    def _persist_ai_analysis(self, result: AnalysisResult) -> None:
        """Connects to the PostgreSQL database and inserts the complete analysis result."""
        self.logger.info(
            f"Persisting AI analysis for {result.procurement_control_number}..."
        )

        conn = None
        cursor = None
        try:
            db_config = self.logger.config
            conn = psycopg2.connect(
                dbname=db_config.POSTGRES_DB,
                user=db_config.POSTGRES_USER,
                password=db_config.POSTGRES_PASSWORD,
                host=db_config.POSTGRES_HOST,
                port=db_config.POSTGRES_PORT,
            )
            cursor = conn.cursor()

            sql_insert = """
                INSERT INTO procurement_analysis (
                    procurement_control_number, risk_score, summary,
                    red_flags, warnings, gcs_document_url
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (procurement_control_number) DO UPDATE SET
                    risk_score = EXCLUDED.risk_score,
                    summary = EXCLUDED.summary,
                    red_flags = EXCLUDED.red_flags,
                    warnings = EXCLUDED.warnings,
                    gcs_document_url = EXCLUDED.gcs_document_url,
                    analysis_date = CURRENT_TIMESTAMP;
            """

            # Use model_dump to get a dictionary, then json.dumps for the JSONB field
            red_flags_json = json.dumps(
                result.ai_analysis.model_dump(include={"red_flags"})
            )

            data = (
                result.procurement_control_number,
                result.ai_analysis.risk_score,
                result.ai_analysis.summary,
                red_flags_json,
                result.warnings,
                result.gcs_document_url,
            )

            cursor.execute(sql_insert, data)
            conn.commit()
            self.logger.info("AI analysis successfully persisted.")
        except psycopg2.Error as e:
            self.logger.error(f"Database error during AI analysis insertion: {e}")
            if conn:
                conn.rollback()
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def run_analysis(self, start_date: date, end_date: date):
        """
        Runs the Public Detective analysis job for the specified date range.

        It iterates through each day in the range, fetches all procurements
        that were updated on that day, and publishes each one to a Pub/Sub topic.

        :param start_date: The start date for the analysis.
        :param end_date: The end date for the analysis.
        """
        self.logger.info(
            f"Starting analysis job for date range: {start_date} to {end_date}"
        )

        current_date = start_date
        while current_date <= end_date:
            self.logger.info(f"Processing date: {current_date}")

            updated_procurements = self.procurement_repo.get_updated_procurements(
                target_date=current_date
            )

            if not updated_procurements:
                self.logger.info(
                    f"No procurements were updated on {current_date}. Moving to next day."
                )
                current_date += timedelta(days=1)
                continue

            self.logger.info(
                f"Found {len(updated_procurements)} updated procurements. Publishing to message queue."
            )

            success_count = 0
            failure_count = 0

            for procurement in updated_procurements:
                published = self.procurement_repo.publish_procurement_to_pubsub(
                    procurement
                )
                if published:
                    success_count += 1
                    # break  # TO DO: Remove this break to process all procurements
                else:
                    failure_count += 1

            self.logger.info(
                f"Finished processing for {current_date}. "
                f"Successfully published: {success_count}, Failures: {failure_count}"
            )

            current_date += timedelta(days=1)

        self.logger.info("Analysis job for the entire date range has been completed.")
