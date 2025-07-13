from datetime import date, timedelta

from providers.logging import Logger, LoggingProvider
from repositories.procurement import ProcurementRepository


class AnalysisService:
    """
    Service for running Public Detective analysis jobs.

    This service orchestrates the process of fetching updated procurements
    and publishing them to a message queue for asynchronous analysis.
    """

    procurement_repo: ProcurementRepository
    logger: Logger

    def __init__(self):
        """
        Initializes the service with its dependencies.
        """
        self.procurement_repo = ProcurementRepository()
        self.logger = LoggingProvider().get_logger()

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
                else:
                    failure_count += 1

            self.logger.info(
                f"Finished processing for {current_date}."
                f"Successfully published: {success_count}, Failures: {failure_count}"
            )

            current_date += timedelta(days=1)

        self.logger.info("Analysis job for the entire date range has been completed.")
