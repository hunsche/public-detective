"""
This module defines the repository for handling database operations
related to procurement analysis results.
"""

import json
from contextlib import contextmanager

from models.analysis import Analysis, AnalysisResult
from providers.database import DatabaseProvider
from providers.logging import Logger, LoggingProvider
from pydantic import ValidationError


class AnalysisRepository:
    """
    Handles all database operations related to procurement analysis.
    """

    def __init__(self) -> None:
        """
        Initializes the repository and gets a reference to the connection pool.
        """
        self.logger: Logger = LoggingProvider().get_logger()
        self.pool = DatabaseProvider.get_pool()

    @contextmanager
    def get_connection(self):
        """
        Provides a managed database connection from the pool.
        """
        conn = self.pool.getconn()
        try:
            yield conn
        finally:
            self.pool.putconn(conn)

    def _parse_row_to_model(self, row: tuple, columns: list[str]) -> AnalysisResult | None:
        """
        Parses a database row into an AnalysisResult Pydantic model.
        """
        if not row:
            return None

        row_dict = dict(zip(columns, row))

        try:
            ai_analysis_data = {
                "risk_score": row_dict.get("risk_score"),
                "risk_score_rationale": row_dict.get("risk_score_rationale"),
                "summary": row_dict.get("summary"),
                "red_flags": json.loads(row_dict.get("red_flags", "[]")),
            }
            row_dict["ai_analysis"] = Analysis(**ai_analysis_data)

            return AnalysisResult.model_validate(row_dict)
        except (ValidationError, json.JSONDecodeError) as e:
            self.logger.error(f"Failed to parse analysis result from DB: {e}")
            return None

    def save_analysis(self, result: AnalysisResult) -> None:
        """
        Saves a complete analysis result to the database using an 'upsert' operation.
        """
        self.logger.info(f"Saving analysis for {result.procurement_control_number}.")

        sql = """
            INSERT INTO procurement_analysis (
                procurement_control_number, document_hash, risk_score,
                risk_score_rationale, summary, red_flags, warnings,
                original_documents_url, processed_documents_url
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (procurement_control_number) DO UPDATE SET
                document_hash = EXCLUDED.document_hash,
                risk_score = EXCLUDED.risk_score,
                risk_score_rationale = EXCLUDED.risk_score_rationale,
                summary = EXCLUDED.summary,
                red_flags = EXCLUDED.red_flags,
                warnings = EXCLUDED.warnings,
                original_documents_url = EXCLUDED.original_documents_url,
                processed_documents_url = EXCLUDED.processed_documents_url,
                analysis_date = CURRENT_TIMESTAMP;
        """

        red_flags_json = result.ai_analysis.model_dump_json(include={"red_flags"})

        params = (
            result.procurement_control_number,
            result.document_hash,
            result.ai_analysis.risk_score,
            result.ai_analysis.risk_score_rationale,
            result.ai_analysis.summary,
            red_flags_json,
            result.warnings,
            result.original_documents_url,
            None,  # processed_documents_url is no longer used
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
        sql = "SELECT * FROM procurement_analysis WHERE document_hash = %s LIMIT 1;"

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (document_hash,))
                if cur.rowcount == 0:
                    return None
                columns = [desc[0] for desc in cur.description]
                row = cur.fetchone()

        return self._parse_row_to_model(row, columns)
