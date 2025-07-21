import uuid
from datetime import date, timedelta

from models.analysis import Analysis
from models.procurement import Procurement
from providers.ai import AiProvider
from providers.gcs import GcsProvider
from providers.logging import Logger, LoggingProvider
from repositories.procurement import ProcurementRepository


class AnalysisService:
    """Service to orchestrate ETL jobs and the analysis of individual procurements.

    This class contains the core business logic for both fetching daily
    procurement data and for processing a single procurement message from the
    worker queue. It acts as a central coordinator between the data repository
    and the AI provider.
    """

    procurement_repository: ProcurementRepository
    logger: Logger
    ai_provider: AiProvider[Analysis]
    gcs_provider: GcsProvider

    def __init__(self) -> None:
        """Initializes the service and its dependencies.

        This constructor creates a specialized instance of the AiProvider,
        configured to expect the Analysis schema for all its outputs.
        """
        self.procurement_repository = ProcurementRepository()
        self.logger = LoggingProvider().get_logger()
        self.ai_provider = AiProvider(Analysis)
        self.gcs_provider = GcsProvider()

    def analyze_procurement(self, procurement: Procurement) -> None:
        """Executes the full analysis pipeline for a single procurement.

        This involves downloading and aggregating all documents into a single
        ZIP archive, sending it for AI analysis, uploading the artifact to GCS,
        and persisting the outcome.

        Args:
            procurement: The procurement data object to be analyzed.
        """
        control_number = procurement.pncp_control_number
        self.logger.info(f"Starting analysis for procurement {control_number}...")

        zip_content = self.procurement_repository.get_document_content_as_zip(procurement)
        if not zip_content:
            self.logger.warning(
                f"No document content for {control_number}. Skipping analysis."
            )
            return

        file_name_uuid = f"{uuid.uuid4()}.zip"

        try:
            # document_url = self._upload_document_to_gcs(zip_content, file_name_uuid)

            prompt = self._build_analysis_prompt(procurement)

            analysis_result = self.ai_provider.get_structured_analysis(
                prompt=prompt,
                file_content=zip_content,
                file_display_name=f"{control_number.replace('/', '_')}.zip",
            )

            self.logger.info(f"Successfully received analysis for {control_number}.")
            self.logger.info(f"Risk Score: {analysis_result.risk_score}")

            self._persist_analysis_result(procurement, analysis_result, "document_url")

        except Exception as e:
            self.logger.error(f"AI analysis pipeline failed for {control_number}: {e}")
            raise

    def _upload_document_to_gcs(self, pdf_content: bytes, destination_name: str) -> str:
        """Uploads the merged PDF content to GCS using a generated UUID as the filename.

        Args:
            pdf_content: The raw byte content of the PDF.
            destination_name: The unique filename (including extension) for the GCS object.

        Returns:
            The public URL of the uploaded file.
        """
        bucket_name = self.gcs_provider.config.GCP_GCS_BUCKET_PROCUREMENTS
        return self.gcs_provider.upload_file(
            bucket_name=bucket_name,
            destination_blob_name=destination_name,
            content=pdf_content,
            content_type="application/pdf",
        )

    def _persist_analysis_result(
        self, procurement: Procurement, analysis: Analysis, document_url: str
    ) -> None:
        """Placeholder for the logic to save analysis results and the document
        URL to the database.

        Args:
            procurement: The original procurement data model.
            analysis: The structured analysis result from the AI.
            document_url: The public URL of the merged PDF stored in GCS.
        """
        self.logger.info(f"Persisting analysis for {procurement.pncp_control_number}...")
        self.logger.info(f"Document available at: {document_url}")
        self.logger.info("Persistence step completed (simulation).")

    def _build_analysis_prompt(self, procurement: Procurement) -> str:
        """Constructs the detailed, business-specific prompt for the AI model."""
        procurement_json = procurement.model_dump_json(by_alias=True, indent=2)
        return f"""
        You are a senior auditor specializing in public procurement in Brazil,
        with deep knowledge of Law No. 14.133/2021. Your task is to analyze
        the provided PDF bid document to identify potential irregularities.

        First, review the procurement's metadata in JSON format for context.
        Then, analyze the full content of the attached bid document (which may
        contain a merged edital and its annexes).

        --- PROCUREMENT METADATA (JSON) ---
        {procurement_json}
        --- END OF METADATA ---

        Based on both the metadata and the PDF content, analyze the bid for
        irregularities in the following categories. For each finding, you must
        extract the exact quote that supports your analysis.

        1.  Vendor-Specific Directing (DIRECTING): (e.g., brand requirements,
            restrictive specifications).
        2.  Restriction of Competitiveness (COMPETITION_RESTRICTION): (e.g.,
            tight deadlines, excessive qualifications, improper item grouping).
        3.  Potential for Overpricing (OVERPRICE): (e.g., items without unit
            prices, ambiguous judgment criteria).

        Your response must be a JSON object that strictly adheres to the
        provided schema.
        """

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

            updated_procurements = self.procurement_repository.get_updated_procurements(
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
                published = self.procurement_repository.publish_procurement_to_pubsub(
                    procurement
                )
                if published:
                    success_count += 1
                    break  # TO DO: Remove this break to process all procurements
                else:
                    failure_count += 1

            self.logger.info(
                f"Finished processing for {current_date}."
                f"Successfully published: {success_count}, Failures: {failure_count}"
            )

            current_date += timedelta(days=1)

        self.logger.info("Analysis job for the entire date range has been completed.")
