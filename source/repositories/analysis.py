"""
This module defines the repository for handling database operations
related to procurement analysis results.
"""

import json
from typing import cast

from models.analysis import Analysis, AnalysisResult
from providers.logging import Logger, LoggingProvider
from pydantic import ValidationError
from sqlalchemy import Engine, text


class AnalysisRepository:
    """
    Handles all database operations related to procurement analysis.
    """

    logger: Logger
    engine: Engine

    def __init__(self, engine: Engine) -> None:
        """
        Initializes the repository with a database engine.
        """
        self.logger = LoggingProvider().get_logger()
        self.engine = engine

    def _parse_row_to_model(self, row: tuple, columns: list[str]) -> AnalysisResult | None:
        """
        Parses a database row into an AnalysisResult Pydantic model.
        """
        if not row:
            return None

        row_dict = dict(zip(columns, row))
        red_flags_data = row_dict.get("red_flags", "[]")
        if isinstance(red_flags_data, str):
            red_flags = json.loads(red_flags_data)
        else:
            red_flags = red_flags_data

        try:
            ai_analysis_data = {
                "risk_score": row_dict.get("risk_score"),
                "risk_score_rationale": row_dict.get("risk_score_rationale"),
                "summary": row_dict.get("summary"),
                "red_flags": red_flags,
            }
            row_dict["ai_analysis"] = Analysis(**ai_analysis_data)

            return AnalysisResult.model_validate(row_dict)
        except (ValidationError, json.JSONDecodeError) as e:
            self.logger.error(f"Failed to parse analysis result from DB: {e}")
            return None

    def save_analysis(self, result: AnalysisResult) -> int:
        """
        Saves a complete analysis result to the database and returns the new
        record's ID.
        """
        self.logger.info(f"Saving analysis for {result.procurement_control_number}.")

        sql = text(
            """
            INSERT INTO procurement_analysis (
                procurement_control_number, document_hash, risk_score,
                risk_score_rationale, summary, red_flags, warnings,
                original_documents_gcs_path, processed_documents_gcs_path
            ) VALUES (
                :procurement_control_number, :document_hash, :risk_score,
                :risk_score_rationale, :summary, :red_flags, :warnings,
                :original_documents_gcs_path, :processed_documents_gcs_path
            )
            RETURNING id;
        """
        )

        red_flags_json = json.dumps([rf.model_dump() for rf in result.ai_analysis.red_flags])

        params = {
            "procurement_control_number": result.procurement_control_number,
            "document_hash": result.document_hash,
            "risk_score": result.ai_analysis.risk_score,
            "risk_score_rationale": result.ai_analysis.risk_score_rationale,
            "summary": result.ai_analysis.summary,
            "red_flags": red_flags_json,
            "warnings": result.warnings,
            "original_documents_gcs_path": result.original_documents_gcs_path,
            "processed_documents_gcs_path": result.processed_documents_gcs_path,
        }

        with self.engine.connect() as conn:
            result_proxy = conn.execute(sql, params)
            analysis_id = cast(int, result_proxy.scalar_one())
            conn.commit()

        self.logger.info(f"Analysis saved successfully with ID: {analysis_id}.")
        return analysis_id

    def get_analysis_by_hash(self, document_hash: str) -> AnalysisResult | None:
        """
        Retrieves an analysis result from the database by its document hash.
        """
        sql = text("SELECT * FROM procurement_analysis WHERE document_hash = :document_hash LIMIT 1;")

        with self.engine.connect() as conn:
            result = conn.execute(sql, {"document_hash": document_hash}).fetchone()
            if not result:
                return None
            columns = list(result._fields)
            row = tuple(result)

        return self._parse_row_to_model(row, columns)
