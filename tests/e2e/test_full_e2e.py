import json
import os
import socket
import subprocess  # nosec B404
import time
import uuid
from collections.abc import Generator
from pathlib import Path
from zipfile import ZipFile

import pytest
from google.api_core import exceptions
from google.auth.credentials import AnonymousCredentials
from google.cloud import pubsub_v1, storage
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from tests.e2e.conftest import run_command








@pytest.fixture(scope="function")
def e2e_test_setup(db_session: Engine) -> Generator:
    """Configures the environment for a single E2E test function.

    Sets up unique Pub/Sub topics, GCS paths, and cleans up afterwards.

    Args:
        db_session: The SQLAlchemy engine instance from the db_session fixture.

    Yields:
        None.
    """
    # Ensure E2E tests for GCS and AI run against real GCP services,
    # while Pub/Sub can still use an emulator.
    os.environ.pop("GCP_GCS_HOST", None)
    os.environ.pop("GCP_AI_HOST", None)

    print("\n--- Setting up E2E test environment ---")
    project_id = "total-entity-463718-k1"
    os.environ["GCP_PROJECT"] = project_id

    bucket_name_for_tests = "vertex-ai-test-files"
    os.environ["GCP_GCS_BUCKET_PROCUREMENTS"] = bucket_name_for_tests
    os.environ["GCP_VERTEX_AI_BUCKET"] = bucket_name_for_tests

    run_id = uuid.uuid4().hex
    topic_name = f"procurements-topic-{run_id}"
    subscription_name = f"procurements-subscription-{run_id}"
    os.environ["GCP_PUBSUB_TOPIC_PROCUREMENTS"] = topic_name
    os.environ["GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS"] = subscription_name
    os.environ["GCP_GCS_TEST_PREFIX"] = f"test-run-{run_id}"

    # Pub/Sub setup
    publisher = pubsub_v1.PublisherClient(credentials=AnonymousCredentials())
    subscriber = pubsub_v1.SubscriberClient(credentials=AnonymousCredentials())
    topic_path = publisher.topic_path(project_id, topic_name)
    subscription_path = subscriber.subscription_path(project_id, subscription_name)

    # GCS setup
    gcs_credentials_path = os.path.expanduser("~/.gcp/credentials.json")
    with open(gcs_credentials_path, "r") as f:
        gcs_credentials_json = f.read()
    os.environ["GCP_SERVICE_ACCOUNT_CREDENTIALS"] = gcs_credentials_json
    gcs_client = storage.Client.from_service_account_json(gcs_credentials_path, project=project_id)
    bucket_name = os.environ.get("GCP_VERTEX_AI_BUCKET", "vertex-ai-test-files")
    bucket = gcs_client.bucket(bucket_name)

    if not bucket.exists():
        pytest.fail(f"GCS bucket '{bucket_name}' does not exist. Please create it before running the E2E test.")
    else:
        print(f"Bucket {bucket_name} exists, clearing contents for test run.")
        for blob in bucket.list_blobs():
            blob.delete()

    try:
        print(f"Creating Pub/Sub topic: {topic_path}")
        publisher.create_topic(request={"name": topic_path})
        print(f"Creating Pub/Sub subscription: {subscription_path}")
        subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})

        with db_session.connect() as connection:
            print("Truncating tables before test run...")
            connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
            connection.execute(
                text(
                    "TRUNCATE procurements, procurement_analyses, file_records, donations, budget_ledgers RESTART "
                    "IDENTITY CASCADE;"
                )
            )
            connection.commit()
            print("Tables truncated.")

        yield

    finally:
        print("\n--- Tearing down E2E test environment ---")
        try:
            subscriber.delete_subscription(request={"subscription": subscription_path})
            print(f"Deleted subscription: {subscription_name}")
        except exceptions.NotFound:
            print(f"Subscription not found, skipping deletion: {subscription_name}")
        try:
            publisher.delete_topic(request={"topic": topic_path})
            print(f"Deleted topic: {topic_name}")
        except exceptions.NotFound:
            print(f"Topic not found, skipping deletion: {topic_name}")

        try:
            print(f"Clearing GCS objects in bucket: {bucket_name}")
            for blob in bucket.list_blobs():
                blob.delete()
            print(f"Cleared bucket: {bucket_name}")
        except exceptions.NotFound:
            print(f"Bucket not found, skipping cleanup: {bucket_name}")

        print("E2E test environment torn down.")



@pytest.mark.timeout(300)
def test_ranked_analysis_e2e_flow(e2e_test_setup: None, db_session: Engine) -> None:  # noqa: F841
    """Tests the full E2E flow for ranked analysis against live dependencies.

    1. Pre-analyzes procurements, creating analysis records in the DB.
    2. Injects a donation to establish a budget.
    3. Triggers the ranked analysis with auto-budget.
    4. Runs the worker to consume messages.
    5. Validates that analyses were processed and the budget ledger was updated.

    Args:
        e2e_test_setup: The fixture to set up the E2E test environment.
        db_session: The SQLAlchemy engine instance from the db_session fixture.
    """
    print("\n--- Starting E2E test flow ---")
    target_date_str = "2025-08-23"
    ibge_code = "3550308"
    max_items_to_process = 1

    os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"
    os.environ["GCP_GEMINI_PRICE_PER_1K_TOKENS"] = "0.002"
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.expanduser("~/.gcp/credentials.json")

    pre_analyze_command = (
        f"poetry run python -m source.cli pre-analyze "
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

    ranked_analysis_command = (
        "poetry run python -m source.cli trigger-ranked-analysis " "--use-auto-budget --budget-period daily"
    )
    run_command(ranked_analysis_command)

    worker_command = (
        f"poetry run python -m source.worker "
        f"--max-messages {max_items_to_process} "
        f"--timeout 5 "
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
                serializable_records = [{key: str(value) for key, value in record.items()} for record in records]
                print(json.dumps(serializable_records, indent=2, ensure_ascii=False))
    print("\n--- Data Dump Complete ---")
