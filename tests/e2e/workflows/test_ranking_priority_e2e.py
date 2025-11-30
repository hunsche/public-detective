import json
import os
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.e2e.workflows.conftest import GcsCleanupManager, run_command


def test_ranked_priority_flow(
    db_session: Engine, e2e_pubsub: tuple[Any, Any], gcs_cleanup_manager: GcsCleanupManager
) -> None:
    """Runs the ranked analysis flow and validates ranking-specific behaviours."""
    assert e2e_pubsub is not None

    print("\n--- Starting ranked priority E2E test ---")
    target_date_str = "2025-08-23"
    ibge_code = "3550308"
    max_items_to_process = 1
    gcs_prefix = gcs_cleanup_manager.prefix

    os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"

    pre_analyze_command = (
        f"poetry run pd analysis --gcs-path-prefix {gcs_prefix} prepare "
        f"--start-date {target_date_str} --end-date {target_date_str} "
        f"--max-messages {max_items_to_process}"
    )
    run_command(pre_analyze_command)

    print("\n--- Inspecting ranking metadata produced during pre-analysis ---")
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))

        procurements = (
            connection.execute(
                text(
                    "SELECT pncp_control_number, version_number, current_priority_score, "
                    "current_quality_score, current_estimated_cost, current_potential_impact_score, "
                    "is_stable, temporal_score, federal_bonus_score "
                    "FROM procurements ORDER BY created_at DESC"
                )
            )
            .mappings()
            .all()
        )
        assert procurements, "Expected procurements to be saved during pre-analysis."
        assert len(procurements) == max_items_to_process

        # Assuming max_items_to_process is 1, we can assert on the single procurement record
        procurement = procurements[0]
        print(
            "Loaded procurement",
            procurement["pncp_control_number"],
            "priority=",
            procurement["current_priority_score"],
            "quality=",
            procurement["current_quality_score"],
        )
        assert procurement["current_priority_score"] is not None
        assert procurement["current_quality_score"] is not None
        assert procurement["current_estimated_cost"] is not None
        assert procurement["current_potential_impact_score"] is not None
        assert procurement["is_stable"] is True
        assert procurement["temporal_score"] is not None
        assert procurement["federal_bonus_score"] is not None

        analyses = (
            connection.execute(
                text(
                    "SELECT analysis_id, procurement_control_number, version_number, status, total_cost "
                    "FROM procurement_analyses ORDER BY created_at DESC"
                )
            )
            .mappings()
            .all()
        )
        assert analyses, "Expected analysis records after pre-analysis."
        assert len(analyses) == max_items_to_process

        selected_analysis = analyses[0]
        assert selected_analysis["status"] == "PENDING_ANALYSIS"
        analysis_id = uuid.UUID(str(selected_analysis["analysis_id"]))
        control_number = selected_analysis["procurement_control_number"]
        version_number = selected_analysis["version_number"]
        print(
            "Pending analysis",
            analysis_id,
            "for procurement",
            control_number,
            "version",
            version_number,
            "estimated cost=",
            selected_analysis["total_cost"],
        )

        connection.execute(
            text(
                "INSERT INTO donations (id, donor_identifier, amount, transaction_id, created_at) "
                "VALUES (:id, :donor_identifier, :amount, :transaction_id, NOW())"
            ),
            {
                "id": str(uuid.uuid4()),
                "donor_identifier": "RANKING_E2E_DONOR",
                "amount": 25.00,
                "transaction_id": "RANKING_E2E_TX_ID",
            },
        )
        print("--- Inserted mock donation ---")

        connection.execute(
            text(
                "INSERT INTO votes (vote_id, procurement_control_number, version_number, user_id, vote_type) "
                "VALUES (:vote_id, :procurement_control_number, :version_number, :user_id, :vote_type)"
            ),
            {
                "vote_id": str(uuid.uuid4()),
                "procurement_control_number": control_number,
                "version_number": version_number,
                "user_id": str(uuid.uuid4()),
                "vote_type": "UP",
            },
        )
        print("--- Recorded supportive vote for prioritization ---")

        connection.commit()

    ranked_analysis_command = (
        "poetry run pd analysis rank --use-auto-budget --budget-period daily " f"--max-messages {max_items_to_process}"
    )
    run_command(ranked_analysis_command)

    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        status_after_rank = connection.execute(
            text("SELECT status FROM procurement_analyses WHERE analysis_id = :analysis_id"),
            {"analysis_id": str(analysis_id)},
        ).scalar_one()
    assert status_after_rank == "ANALYSIS_IN_PROGRESS"
    print("--- Rank command transitioned analysis to IN_PROGRESS ---")

    worker_command = (
        f"poetry run pd worker start "
        f"--gcs-path-prefix {gcs_prefix} "
        f"--max-messages {max_items_to_process} "
        f"--timeout 15 "
        f"--max-output-tokens None"
    )
    run_command(worker_command)

    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        final_status = (
            connection.execute(
                text("SELECT status, total_cost FROM procurement_analyses WHERE analysis_id = :analysis_id"),
                {"analysis_id": str(analysis_id)},
            )
            .mappings()
            .one()
        )
        assert final_status["status"] == "ANALYSIS_SUCCESSFUL"
        assert final_status["total_cost"] is not None
        print("--- Worker completed analysis with total cost", final_status["total_cost"], "---")

        history_rows = (
            connection.execute(
                text(
                    "SELECT status, details FROM procurement_analysis_status_history "
                    "WHERE analysis_id = :analysis_id ORDER BY created_at"
                ),
                {"analysis_id": str(analysis_id)},
            )
            .mappings()
            .all()
        )
        history_statuses = [row["status"] for row in history_rows]
        assert "PENDING_ANALYSIS" in history_statuses
        assert "ANALYSIS_IN_PROGRESS" in history_statuses
        assert "ANALYSIS_SUCCESSFUL" in history_statuses
        print("--- Status history contains progression:", history_statuses, "---")

        ledger_entries = (
            connection.execute(
                text("SELECT transaction_type, amount, description FROM budget_ledgers ORDER BY created_at")
            )
            .mappings()
            .all()
        )
        assert ledger_entries, "Expected expense entries after successful analysis."
        expense_entries = [entry for entry in ledger_entries if entry["transaction_type"] == "EXPENSE"]
        assert expense_entries, "Expected at least one expense entry in the budget ledger."
        print("--- Budget ledger entries:", ledger_entries, "---")

        votes_registered = (
            connection.execute(
                text(
                    "SELECT vote_id, vote_type FROM votes WHERE procurement_control_number = :control_number "
                    "AND version_number = :version_number"
                ),
                {"control_number": control_number, "version_number": version_number},
            )
            .mappings()
            .all()
        )
        assert votes_registered, "Expected persisted vote record."
        print("--- Votes registered:", votes_registered, "---")

    print("\n--- Critical Analysis Data Dump ---")
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        get_tables_query = text("SELECT tablename FROM pg_tables WHERE schemaname = :schema")
        tables_result = connection.execute(get_tables_query, {"schema": os.environ["POSTGRES_DB_SCHEMA"]})
        table_names = [row[0] for row in tables_result if row[0] != "alembic_version"]

        for table_name in sorted(table_names):
            print(f"\n--- Dumping table: {table_name} ---")
            dump_query = text(f"SELECT * FROM {table_name}")  # nosec B608
            records = connection.execute(dump_query).mappings().all()
            if not records:
                print("[]")
            else:
                serializable_records = [dict(record) for record in records]
                print(json.dumps(serializable_records, indent=2, ensure_ascii=False, default=str))
    print("\n--- Ranked priority E2E test completed successfully ---")
