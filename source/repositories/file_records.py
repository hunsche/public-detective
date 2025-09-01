"""This module defines the repository for file records management."""
from models.file_records import NewFileRecord
from providers.logging import Logger, LoggingProvider
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

    def save_file_record(self, record: NewFileRecord) -> None:
        """Saves a new file record to the database.

        This method takes a `NewFileRecord` object, which contains all the
        necessary metadata about a file, and inserts it into the
        `file_records` table.

        Args:
            record: A `NewFileRecord` object containing the data to be saved.
        """
        self.logger.info(f"Saving file record for {record.file_name}.")

        sql = text(
            """
            INSERT INTO file_records (
                analysis_id, file_name, gcs_path, extension, size_bytes,
                nesting_level, included_in_analysis, exclusion_reason,
                prioritization_logic
            ) VALUES (
                :analysis_id, :file_name, :gcs_path, :extension, :size_bytes,
                :nesting_level, :included_in_analysis, :exclusion_reason,
                :prioritization_logic
            );
        """
        )

        params = record.model_dump()

        with self.engine.connect() as conn:
            conn.execute(sql, params)
            conn.commit()

        self.logger.info("File record saved successfully.")
