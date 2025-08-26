from models.file_record import NewFileRecord
from providers.database import DatabaseManager
from providers.logging import Logger, LoggingProvider
from sqlalchemy import text


class FileRecordRepository:
    """
    Handles all database operations related to file records.
    """

    def __init__(self) -> None:
        """
        Initializes the repository and gets a reference to the database engine.
        """
        self.logger: Logger = LoggingProvider().get_logger()
        self.engine = DatabaseManager.get_engine()

    def save_file_record(self, record: NewFileRecord) -> None:
        """
        Saves a file record to the database.
        """
        self.logger.info(f"Saving file record for {record.file_name}.")

        sql = text(
            """
            INSERT INTO file_record (
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
