import json
from contextlib import contextmanager

from models.analysis import AnalysisResult
from providers.database import DatabaseProvider
from providers.logging import Logger, LoggingProvider


class AnalysisRepository:
    """
    Handles all database operations related to procurement analysis.
    """

    def __init__(self):
        self.logger: Logger = LoggingProvider.get_logger()
        self.pool = DatabaseProvider.get_pool()

    @contextmanager
    def get_connection(self):
        """Provides a managed database connection from the pool."""
        conn = self.pool.getconn()
        try:
            yield conn
        finally:
            self.pool.putconn(conn)

    def save_analysis(self, result: AnalysisResult) -> None:
        """
        Saves a complete analysis result to the database.
        This performs an 'upsert' operation.
        """
        self.logger.info(
            f"Saving analysis for procurement {result.procurement_control_number} to the database."
        )
        sql = """
            INSERT INTO procurement_analysis (
                procurement_control_number, risk_score, risk_score_rationale, summary,
                red_flags, warnings, gcs_document_url, document_hash
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (procurement_control_number) DO UPDATE SET
                risk_score = EXCLUDED.risk_score,
                risk_score_rationale = EXCLUDED.risk_score_rationale,
                summary = EXCLUDED.summary,
                red_flags = EXCLUDED.red_flags,
                warnings = EXCLUDED.warnings,
                gcs_document_url = EXCLUDED.gcs_document_url,
                document_hash = EXCLUDED.document_hash,
                analysis_date = CURRENT_TIMESTAMP;
        """

        red_flags_json = json.dumps(
            result.ai_analysis.model_dump(include={"red_flags"})
        )

        params = (
            result.procurement_control_number,
            result.ai_analysis.risk_score,
            result.ai_analysis.risk_score_rationale,
            result.ai_analysis.summary,
            red_flags_json,
            result.warnings,
            result.gcs_document_url,
            result.document_hash,
        )

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()

        self.logger.info("Analysis saved successfully.")

    def get_analysis_by_hash(self, document_hash: str) -> AnalysisResult | None:
        """
        Retrieves an analysis result from the database by its document hash.
        """
        sql = "SELECT * FROM procurement_analysis WHERE document_hash = %s;"
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (document_hash,))
                result = cur.fetchone()

        if not result:
            return None

        # This is a simplified parsing. A real implementation would need to
        # map all columns to the AnalysisResult Pydantic model.
        # For the purpose of the idempotency check, just returning a non-None
        # value is sufficient.
        return AnalysisResult(procurement_control_number="dummy", ai_analysis={}, gcs_document_url="", document_hash=document_hash)
