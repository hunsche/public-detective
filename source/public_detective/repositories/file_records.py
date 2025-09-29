"""This module defines the repository for file records management."""

from typing import Any
from uuid import UUID

from public_detective.models.file_records import NewFileRecord
from public_detective.providers.logging import Logger, LoggingProvider
from sqlalchemy import Engine, text


class FileRecordsRepository:
    """Handles database operations for file records.

    This repository is responsible for persisting metadata about every file
    processed during a procurement analysis, whether it was included in the
    AI analysis or not.

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

    def save_file_record(self, file_record: NewFileRecord) -> UUID:
        """Saves a file record to the database.

        Args:
            file_record: The file record to save.

        Returns:
            The UUID of the newly created file record.
        """
        self.logger.info(f"Saving file record for {file_record.file_name}.")
        sql = text(
            """
            INSERT INTO file_records (
                source_document_id, file_name, gcs_path, extension, size_bytes,
                nesting_level, included_in_analysis, exclusion_reason,
                prioritization_logic, prepared_content_gcs_uris
            ) VALUES (
                :source_document_id, :file_name, :gcs_path, :extension, :size_bytes,
                :nesting_level, :included_in_analysis, :exclusion_reason,
                :prioritization_logic, :prepared_content_gcs_uris
            ) RETURNING id;
        """
        )
        with self.engine.connect() as conn:
            record_id: UUID = conn.execute(sql, parameters=file_record.model_dump()).scalar_one()
            conn.commit()
            return record_id

    def set_files_as_included(self, file_ids: list[UUID]) -> None:
        """Sets the `included_in_analysis` flag to True for a list of file IDs.

        Args:
            file_ids: A list of file record UUIDs to update.
        """
        if not file_ids:
            return

        self.logger.info(f"Marking {len(file_ids)} file(s) as included in the analysis.")
        sql = text(
            """
            UPDATE file_records
            SET included_in_analysis = TRUE
            WHERE id = ANY(:file_ids);
        """
        )
        with self.engine.connect() as conn:
            conn.execute(sql, {"file_ids": file_ids})
            conn.commit()
        self.logger.info("File records updated successfully.")

    def get_all_file_records_by_analysis_id(self, analysis_id: str) -> list[dict[str, Any]]:
        """Retrieves all file records for a given analysis ID.

        Args:
            analysis_id: The ID of the analysis to retrieve file records for.

        Returns:
            A list of file records, where each record is a dictionary-like object.
        """
        self.logger.info(f"Fetching all file records for analysis_id {analysis_id}.")
        sql = text(
            """
            SELECT * FROM file_records WHERE analysis_id = :analysis_id;
            """
        )
        with self.engine.connect() as conn:
            result = conn.execute(sql, {"analysis_id": analysis_id}).mappings().all()
        return [dict(row) for row in result]
