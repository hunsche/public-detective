"""
This module defines the repository for handling database operations
related to procurement analysis results.
"""

import json
from typing import cast

from models.analyses import Analysis, AnalysisResult
from models.procurement_analysis_status import ProcurementAnalysisStatus
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
        red_flags_data = row_dict.get("red_flags")
        if red_flags_data is None:
            red_flags = []
        elif isinstance(red_flags_data, str):
            red_flags = json.loads(red_flags_data)
        else:
            red_flags = red_flags_data

        warnings_data = row_dict.get("warnings")
        if warnings_data is None:
            warnings = []
        else:
            warnings = warnings_data

        try:
            ai_analysis_data = {
                "risk_score": row_dict.get("risk_score"),
                "risk_score_rationale": row_dict.get("risk_score_rationale"),
                "red_flags": red_flags,
            }
            row_dict["ai_analysis"] = Analysis.model_validate(ai_analysis_data)
            row_dict["warnings"] = warnings

            return AnalysisResult.model_validate(row_dict)
        except ValidationError as e:
            self.logger.error(f"Failed to parse analysis result from DB due to validation error: {e}")
            return None

    def save_analysis(self, analysis_id: int, result: AnalysisResult) -> None:
        """
        Updates an existing analysis record with the results of a full analysis.
        """
        self.logger.info(f"Updating analysis for analysis_id {analysis_id}.")

        sql = text(
            """
            UPDATE procurement_analyses
            SET
                document_hash = :document_hash,
                risk_score = :risk_score,
                risk_score_rationale = :risk_score_rationale,
                red_flags = :red_flags,
                warnings = :warnings,
                original_documents_gcs_path = :original_documents_gcs_path,
                processed_documents_gcs_path = :processed_documents_gcs_path,
                status = :status,
                updated_at = now()
            WHERE analysis_id = :analysis_id;
        """
        )

        red_flags_json = json.dumps([rf.model_dump() for rf in result.ai_analysis.red_flags])

        params = {
            "analysis_id": analysis_id,
            "document_hash": result.document_hash,
            "risk_score": result.ai_analysis.risk_score,
            "risk_score_rationale": result.ai_analysis.risk_score_rationale,
            "red_flags": red_flags_json,
            "warnings": result.warnings,
            "original_documents_gcs_path": result.original_documents_gcs_path,
            "processed_documents_gcs_path": result.processed_documents_gcs_path,
            "status": ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL.value,
        }

        with self.engine.connect() as conn:
            conn.execute(sql, params)
            conn.commit()

        self.logger.info(f"Analysis updated successfully for ID: {analysis_id}.")

    def get_analysis_by_hash(self, document_hash: str) -> AnalysisResult | None:
        """
        Retrieves an analysis result from the database by its document hash.
        """
        sql = text(
            "SELECT * FROM procurement_analyses "
            "WHERE document_hash = :document_hash AND status = :status "
            "LIMIT 1;"
        )

        with self.engine.connect() as conn:
            result = conn.execute(
                sql,
                {
                    "document_hash": document_hash,
                    "status": ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL.value,
                },
            ).fetchone()
            if not result:
                return None
            columns = list(result._fields)
            row = tuple(result)

        return self._parse_row_to_model(row, columns)

    def save_pre_analysis(
        self, procurement_control_number: str, version_number: int, estimated_cost: float, document_hash: str
    ) -> int:
        """
        Saves a pre-analysis record to the database.
        """
        self.logger.info(f"Saving pre-analysis for {procurement_control_number} version {version_number}.")
        sql = text(
            """
            INSERT INTO procurement_analyses (
                procurement_control_number, version_number, estimated_cost,
                status, document_hash
            ) VALUES (
                :procurement_control_number, :version_number, :estimated_cost,
                :status, :document_hash
            )
            RETURNING analysis_id;
            """
        )
        params = {
            "procurement_control_number": procurement_control_number,
            "version_number": version_number,
            "estimated_cost": estimated_cost,
            "document_hash": document_hash,
            "status": ProcurementAnalysisStatus.PENDING_ANALYSIS.value,
        }
        with self.engine.connect() as conn:
            result_proxy = conn.execute(sql, params)
            analysis_id = cast(int, result_proxy.scalar_one())
            conn.commit()
        self.logger.info(f"Pre-analysis saved successfully with ID: {analysis_id}.")
        return analysis_id

    def get_analysis_by_id(self, analysis_id: int) -> AnalysisResult | None:
        """
        Retrieves an analysis result from the database by its ID.
        """
        sql = text("SELECT * FROM procurement_analyses WHERE analysis_id = :analysis_id LIMIT 1;")

        with self.engine.connect() as conn:
            result = conn.execute(sql, {"analysis_id": analysis_id}).fetchone()
            if not result:
                return None
            columns = list(result._fields)
            row = tuple(result)

        return self._parse_row_to_model(row, columns)

    def update_analysis_status(self, analysis_id: int, status: ProcurementAnalysisStatus) -> None:
        """
        Updates the status of an analysis record.
        """
        self.logger.info(f"Updating status for analysis {analysis_id} to {status}.")
        sql = text(
            """
            UPDATE procurement_analyses
            SET status = :status, updated_at = now()
            WHERE analysis_id = :analysis_id;
            """
        )
        with self.engine.connect() as conn:
            conn.execute(sql, {"analysis_id": analysis_id, "status": status.value})
            conn.commit()
        self.logger.info("Analysis status updated successfully.")
