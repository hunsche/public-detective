from models.file_record import NewFileRecord
from providers.logging import Logger, LoggingProvider
from sqlalchemy import Engine, text


class FileRecordRepository:
    """
    Handles all database operations related to file records.
    """

    logger: Logger
    engine: Engine

    def __init__(self, engine: Engine) -> None:
        """
        Initializes the repository with a database engine.
        """
        self.logger = LoggingProvider().get_logger()
        self.engine = engine

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
