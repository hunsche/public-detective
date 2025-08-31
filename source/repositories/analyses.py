"""
This module defines the repository for handling database operations
related to procurement analysis results.
"""

import json
from typing import Any, cast

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
            """
            SELECT
                analysis_id,
                procurement_control_number,
                version_number,
                status,
                risk_score,
                risk_score_rationale,
                summary,
                red_flags,
                warnings,
                document_hash,
                original_documents_gcs_path,
                processed_documents_gcs_path,
                estimated_cost,
                created_at,
                updated_at
            FROM procurement_analyses
            WHERE document_hash = :document_hash AND status = :status
            LIMIT 1;
            """
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
        sql = text(
            """
            SELECT
                analysis_id,
                procurement_control_number,
                version_number,
                status,
                risk_score,
                risk_score_rationale,
                summary,
                red_flags,
                warnings,
                document_hash,
                original_documents_gcs_path,
                processed_documents_gcs_path,
                estimated_cost,
                created_at,
                updated_at
            FROM procurement_analyses
            WHERE analysis_id = :analysis_id
            LIMIT 1;
            """
        )

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

    def reset_stale_analyses(self, timeout_minutes: int) -> list[int]:
        """
        Finds analyses that are 'IN_PROGRESS' for longer than the timeout
        and resets their status to 'TIMEOUT'.
        """
        self.logger.info(f"Resetting analyses that have been in progress for more than {timeout_minutes} minutes.")
        sql = text(
            """
            UPDATE procurement_analyses
            SET status = :new_status, updated_at = NOW()
            WHERE
                status = :old_status
                AND updated_at < NOW() - (INTERVAL '1 minute' * :timeout_minutes)
            RETURNING analysis_id;
            """
        )
        params = {
            "new_status": ProcurementAnalysisStatus.TIMEOUT.value,
            "old_status": ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS.value,
            "timeout_minutes": timeout_minutes,
        }
        with self.engine.connect() as conn:
            result = conn.execute(sql, params)
            stale_ids = [row[0] for row in result]
            conn.commit()

        if stale_ids:
            self.logger.info(f"Reset {len(stale_ids)} stale analyses: {stale_ids}")
        else:
            self.logger.info("No stale analyses found.")

        return stale_ids

    def get_procurement_overall_status(self, procurement_control_number: str) -> dict[str, Any] | None:
        """
        Retrieves the overall status of a procurement based on its analysis history.

        This method executes a complex query that determines the single, most relevant
        status for a procurement, considering all its versions and analysis states.

        Args:
            procurement_control_number: The unique control number of the procurement.

        Returns:
            A dictionary containing the 'procurement_id', 'latest_version', and
            'overall_status', or None if the procurement is not found.
        """
        sql = text(
            """
            WITH latest_procurement AS (
              SELECT
                pncp_control_number,
                MAX(version_number) AS latest_version
              FROM procurements
              WHERE pncp_control_number = :pncp_control_number
              GROUP BY pncp_control_number
            ),
            analysis_status_per_version AS (
              SELECT
                procurement_analyses.procurement_control_number,
                procurement_analyses.version_number,
                BOOL_OR(procurement_analyses.status::text = 'ANALYSIS_SUCCESSFUL') AS version_has_success,
                BOOL_OR(procurement_analyses.status::text = 'ANALYSIS_IN_PROGRESS') AS version_has_in_progress,
                BOOL_OR(procurement_analyses.status::text = 'ANALYSIS_FAILED')     AS version_has_failed,
                BOOL_OR(procurement_analyses.status::text = 'PENDING_ANALYSIS')    AS version_has_pending
              FROM procurement_analyses
              WHERE procurement_analyses.procurement_control_number = :pncp_control_number
              GROUP BY
                procurement_analyses.procurement_control_number,
                procurement_analyses.version_number
            ),
            any_previous_version_analyzed AS (
              SELECT
                latest_procurement.pncp_control_number,
                BOOL_OR(analysis_status_per_version.version_has_success) AS has_success_in_previous_versions
              FROM latest_procurement
              JOIN analysis_status_per_version
                ON analysis_status_per_version.procurement_control_number = latest_procurement.pncp_control_number
               AND analysis_status_per_version.version_number < latest_procurement.latest_version
              GROUP BY latest_procurement.pncp_control_number
            ),
            latest_version_status_rollup AS (
              SELECT
                latest_procurement.pncp_control_number,
                latest_procurement.latest_version,
                COALESCE(analysis_status_per_version.version_has_success, false)     AS latest_version_has_success,
                COALESCE(analysis_status_per_version.version_has_in_progress, false) AS latest_version_has_in_progress,
                COALESCE(analysis_status_per_version.version_has_failed, false)      AS latest_version_has_failed,
                COALESCE(analysis_status_per_version.version_has_pending, false)     AS latest_version_has_pending
              FROM latest_procurement
              LEFT JOIN analysis_status_per_version
                ON analysis_status_per_version.procurement_control_number = latest_procurement.pncp_control_number
               AND analysis_status_per_version.version_number = latest_procurement.latest_version
            )
            SELECT
              latest_version_status_rollup.pncp_control_number AS procurement_id,
              latest_version_status_rollup.latest_version,
              CASE
                WHEN latest_version_status_rollup.latest_version_has_in_progress THEN 'ANALYSIS_IN_PROGRESS'
                WHEN latest_version_status_rollup.latest_version_has_success     THEN 'ANALYZED_CURRENT'
                WHEN latest_version_status_rollup.latest_version_has_failed      THEN 'FAILED_CURRENT'
                WHEN
                    any_previous_version_analyzed.has_success_in_previous_versions IS TRUE
                THEN 'ANALYZED_OUTDATED'
                WHEN
                    latest_version_status_rollup.latest_version_has_pending OR
                    latest_version_status_rollup.latest_version IS NOT NULL
                THEN 'PENDING'
                ELSE 'NOT_ANALYZED'
              END AS overall_status
            FROM latest_version_status_rollup
            LEFT JOIN any_previous_version_analyzed
              ON any_previous_version_analyzed.pncp_control_number = latest_version_status_rollup.pncp_control_number;
            """
        )

        with self.engine.connect() as conn:
            result = conn.execute(sql, {"pncp_control_number": procurement_control_number}).fetchone()

        if not result:
            return None

        return dict(result._mapping)
