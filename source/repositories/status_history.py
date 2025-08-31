from sqlalchemy import Engine, text

from source.models.procurement_analysis_status import ProcurementAnalysisStatus
from source.providers.logging import Logger, LoggingProvider


class StatusHistoryRepository:
    """
    Handles all database operations related to the procurement_analysis_status_history table.
    """

    logger: Logger
    engine: Engine

    def __init__(self, engine: Engine) -> None:
        """
        Initializes the repository with a database engine.
        """
        self.logger = LoggingProvider().get_logger()
        self.engine = engine

    def create_record(self, analysis_id: int, status: ProcurementAnalysisStatus, details: str | None = None) -> None:
        """
        Creates a new status history record.
        """
        self.logger.info(f"Recording new status '{status.value}' for analysis_id {analysis_id}.")
        sql = text(
            """
            INSERT INTO procurement_analysis_status_history (analysis_id, status, details)
            VALUES (:analysis_id, :status, :details);
            """
        )
        params = {
            "analysis_id": analysis_id,
            "status": status.value,
            "details": details,
        }
        with self.engine.connect() as conn:
            conn.execute(sql, params)
            conn.commit()
        self.logger.info("Status history record created successfully.")
