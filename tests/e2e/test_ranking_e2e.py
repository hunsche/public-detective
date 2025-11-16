import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.e2e.conftest import GcsCleanupManager, run_command


def test_ranking_logic_e2e(
    db_session: Engine, e2e_pubsub: tuple[Any, Any], gcs_cleanup_manager: GcsCleanupManager
) -> None:
    """Tests the ranking logic E2E flow against live dependencies.

    1. Pre-analyzes procurements to populate the database.
    2. Runs the rank command to calculate priority scores.
    3. Validates that the priority_score has been calculated and stored correctly.

    Args:
        db_session: The SQLAlchemy engine instance from the db_session fixture.
        e2e_pubsub: The tuple containing the Pub/Sub client and topic name.
        gcs_cleanup_manager: The GCS cleanup manager fixture.
    """
    assert e2e_pubsub is not None

    print("\n--- Starting Ranking E2E test flow ---")
    target_date_str = "2025-08-23"
    ibge_code = "3550308"
    max_items_to_process = 5

    gcs_prefix = gcs_cleanup_manager.prefix

    os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"

    pre_analyze_command = (
        f"poetry run pd analysis --gcs-path-prefix {gcs_prefix} prepare "
        f"--start-date {target_date_str} --end-date {target_date_str} "
        f"--max-messages {max_items_to_process}"
    )
    run_command(pre_analyze_command)

    # For this test, we don't need a real budget, just triggering the ranking calculation
    ranked_analysis_command = "poetry run pd analysis rank --budget 1.00"
    run_command(ranked_analysis_command)

    print("\n--- Validating ranking data in procurements table ---")
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))

        # Fetch the procurements that should have been ranked
        analyses = (
            connection.execute(
                text("SELECT procurement_control_number, version_number FROM procurement_analyses WHERE status = 'PENDING_ANALYSIS'")
            )
            .mappings()
            .all()
        )
        procurement_keys = [
            (analysis["procurement_control_number"], analysis["version_number"]) for analysis in analyses
        ]
        assert len(procurement_keys) > 0, "No pending analyses found to check for ranking."

        # Dynamically build the VALUES clause for the JOIN
        values_clause = ", ".join([f"(:pcn_{i}, :vn_{i})" for i in range(len(procurement_keys))])

        procurements_query_str = f"""
            SELECT p.pncp_control_number, p.version_number, p.priority_score, p.potential_impact_score, p.quality_score, p.estimated_cost
            FROM procurements p
            JOIN (VALUES {values_clause}) AS v(pncp_control_number, version_number)
            ON p.pncp_control_number = v.pncp_control_number AND p.version_number = v.version_number
            ORDER BY p.priority_score DESC
        """
        procurements_query = text(procurements_query_str)

        # Build the parameters dictionary
        params = {}
        for i, (pcn, vn) in enumerate(procurement_keys):
            params[f"pcn_{i}"] = pcn
            params[f"vn_{i}"] = vn

        ranked_procurements = (
            connection.execute(procurements_query, params).mappings().all()
        )

        assert len(ranked_procurements) == len(procurement_keys)

        print(f"--- Found {len(ranked_procurements)} ranked procurements to validate ---")
        # Validate that scores have been populated
        for proc in ranked_procurements:
            assert proc["priority_score"] is not None, f"Procurement {proc['pncp_control_number']} has NULL priority_score"
            assert proc["potential_impact_score"] is not None
            assert proc["quality_score"] is not None
            assert proc["estimated_cost"] is not None
            assert proc["priority_score"] != 0, f"Procurement {proc['pncp_control_number']} has zero priority_score"

        # Validate that the procurements are ordered by priority_score
        scores = [p["priority_score"] for p in ranked_procurements]
        print(f"Scores found: {scores}")
        assert scores == sorted(scores, reverse=True), "Procurements are not sorted by priority_score in descending order."

    print("\n--- Ranking E2E test flow completed successfully ---")
