"""This module defines the repository for managing analysis status history."""

from uuid import UUID

from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.providers.logging import Logger, LoggingProvider
from sqlalchemy import Engine, text


class StatusHistoryRepository:
    """Handles database operations for analysis status history.

    This repository is responsible for creating records in the
    `procurement_analysis_status_history` table, which serves as an audit
    trail for the lifecycle of each analysis.

    Args:
        engine: An SQLAlchemy Engine instance for database communication.
    """

    logger: Logger
    engine: Engine

    def __init__(self, engine: Engine) -> None:
        """Initializes the repository with a database engine.

        Args:
            engine: The SQLAlchemy Engine to be used for all database
                communications.
        """
        self.logger = LoggingProvider().get_logger()
        self.engine = engine

    def create_record(self, analysis_id: UUID, status: ProcurementAnalysisStatus, details: str | None = None) -> None:
        """Creates a new status history record.

        Args:
            analysis_id: The ID of the analysis this status belongs to.
            status: The new status being recorded.
            details: An optional string providing more context about the
                status change.
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
