import json
import os
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.e2e.conftest import GcsCleanupManager, run_command


def test_ranked_analysis_e2e_flow(
    db_session: Engine, e2e_pubsub: tuple[Any, Any], gcs_cleanup_manager: GcsCleanupManager
) -> None:
    """Tests the full E2E flow for ranked analysis against live dependencies.

    1. Pre-analyzes procurements, creating analysis records in the DB.
    2. Injects a donation to establish a budget.
    3. Triggers the ranked analysis with auto-budget.
    4. Runs the worker to consume messages.
    5. Validates that analyses were processed and the budget ledger was updated.

    Args:
        db_session: The SQLAlchemy engine instance from the db_session fixture.
        e2e_pubsub: The tuple containing the Pub/Sub client and topic name.
        gcs_cleanup_manager: The GCS cleanup manager fixture.
    """
    # The e2e_pubsub fixture is required to set up the Pub/Sub environment
    assert e2e_pubsub is not None

    print("\n--- Starting E2E test flow ---")
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

    print("\n--- Setting up database for ranked analysis ---")
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        connection.execute(
            text(
                "INSERT INTO donations (id, donor_identifier, amount, transaction_id, created_at) "
                "VALUES (:id, :donor_identifier, :amount, :transaction_id, NOW())"
            ),
            [
                {
                    "id": str(uuid.uuid4()),
                    "donor_identifier": "E2E_TEST_DONOR",
                    "amount": 15.00,
                    "transaction_id": "E2E_TEST_TX_ID",
                }
            ],
        )
        connection.commit()
        print("--- Inserted mock donation ---")

    ranked_analysis_command = "poetry run pd analysis rank --use-auto-budget --budget-period daily"
    run_command(ranked_analysis_command)

    worker_command = (
        f"poetry run pd worker start "
        f"--gcs-path-prefix {gcs_prefix} "
        f"--max-messages {max_items_to_process} "
        f"--timeout 15 "
        f"--max-output-tokens None"
    )
    run_command(worker_command)

    print("\n--- Validating data in tables ---")
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))

        completed_analyses = (
            connection.execute(text("SELECT * FROM procurement_analyses WHERE status = 'ANALYSIS_SUCCESSFUL'"))
            .mappings()
            .all()
        )
        print(f"Successfully completed analyses: {len(completed_analyses)}/{max_items_to_process}")
        assert len(completed_analyses) == max_items_to_process, f"Expected {max_items_to_process} successful analyses."

        ledger_entries = connection.execute(text("SELECT * FROM budget_ledgers")).mappings().all()
        assert len(ledger_entries) == max_items_to_process, f"Expected {max_items_to_process} entries in budget_ledgers"
        print(f"--- budget_ledgers table check passed with {len(ledger_entries)} entries ---")

    print("\n--- E2E test flow completed successfully ---")

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
    print("\n--- Data Dump Complete ---")
