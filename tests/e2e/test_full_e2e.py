import json
import os
import socket
import subprocess  # nosec B404
import time
import uuid
from pathlib import Path
from zipfile import ZipFile

import pytest
from google.api_core import exceptions
from google.auth.credentials import AnonymousCredentials
from google.cloud import pubsub_v1
from sqlalchemy import create_engine, text


def run_command(command: str):
    """Executes a shell command and streams its output in real-time."""
    print(f"\n--- Running command: {command} ---")
    process = subprocess.Popen(
        command,
        shell=True,  # nosec B602
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    if process.stdout:
        for line in process.stdout:
            print(line, end="")
    process.wait()
    if process.returncode != 0:
        pytest.fail(f"Command failed with exit code {process.returncode}: {command}")
    print(f"--- Command finished: {command} ---")


@pytest.fixture(scope="session", autouse=True)
def db_session():
    """
    Manages the test database lifecycle.
    This fixture is session-scoped and runs automatically for all tests.
    It creates a unique schema for the test run, applies migrations,
    and cleans up by dropping the schema afterwards.
    """
    print("\n--- Setting up database session ---")
    # Use localhost for services, as docker-compose exposes the ports to the host
    host = "127.0.0.1"
    os.environ["POSTGRES_HOST"] = host
    os.environ["PUBSUB_EMULATOR_HOST"] = f"{host}:8085"
    os.environ["GCP_GCS_HOST"] = f"http://{host}:8086"

    # Database connection details from environment, falling back to defaults
    user = os.getenv("POSTGRES_USER", "user")
    password = os.getenv("POSTGRES_PASSWORD", "password")
    db_name = os.getenv("POSTGRES_DB", "public_detective")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    schema_name = f"test_schema_{uuid.uuid4().hex}"
    os.environ["POSTGRES_DB_SCHEMA"] = schema_name

    # Wait for postgres to be ready
    timeout = 30
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                break
        except (TimeoutError, ConnectionRefusedError):
            time.sleep(1)
    else:
        pytest.fail(f"Could not connect to postgres at {host}:{port} after {timeout} seconds")

    db_url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(db_url)

    try:
        with engine.connect() as connection:
            print(f"Creating schema {schema_name}...")
            connection.execute(text(f"CREATE SCHEMA {schema_name}"))
            connection.commit()

        # Set schema for alembic migrations
        alembic_ini_path = Path("alembic.ini")
        original_alembic_ini = alembic_ini_path.read_text()
        new_alembic_ini = original_alembic_ini.replace(
            "sqlalchemy.url =", f"sqlalchemy.url = {db_url}\nschema_translate_map = {{'public': {schema_name}}}"
        )
        alembic_ini_path.write_text(new_alembic_ini)

        print("Running Alembic migrations...")
        run_command("poetry run alembic upgrade head")

        yield engine

    finally:
        print("\n--- Tearing down database session ---")
        with engine.connect() as connection:
            print(f"Dropping schema {schema_name}...")
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            connection.commit()
        engine.dispose()
        # Restore original alembic.ini
        if "original_alembic_ini" in locals():
            alembic_ini_path.write_text(original_alembic_ini)
        print("Database session torn down.")


@pytest.fixture(scope="function")
def e2e_test_setup(db_session):
    """
    Configures the environment for a single E2E test function.
    Sets up unique Pub/Sub topics, GCS paths, and cleans up afterwards.
    """
    print("\n--- Setting up E2E test environment ---")
    project_id = "public-detective"
    os.environ["GCP_PROJECT"] = project_id
    os.environ["GCP_GCS_BUCKET_PROCUREMENTS"] = "procurements"
    # NOTE: This test assumes a valid GCP_GEMINI_API_KEY is set in the environment.

    run_id = uuid.uuid4().hex
    topic_name = f"procurements-topic-{run_id}"
    subscription_name = f"procurements-subscription-{run_id}"
    os.environ["GCP_PUBSUB_TOPIC_PROCUREMENTS"] = topic_name
    os.environ["GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS"] = subscription_name
    os.environ["GCP_GCS_TEST_PREFIX"] = f"test-run-{run_id}"

    # Setup Pub/Sub topic and subscription using the Python client
    publisher = pubsub_v1.PublisherClient(credentials=AnonymousCredentials())
    subscriber = pubsub_v1.SubscriberClient(credentials=AnonymousCredentials())
    topic_path = publisher.topic_path(project_id, topic_name)
    subscription_path = subscriber.subscription_path(project_id, subscription_name)

    try:
        print(f"Creating Pub/Sub topic: {topic_path}")
        publisher.create_topic(request={"name": topic_path})
        print(f"Creating Pub/Sub subscription: {subscription_path}")
        subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})

        # Truncate tables before the test run for a clean state
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
        # Teardown Pub/Sub
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
        print("E2E test environment torn down.")


@pytest.mark.timeout(240)
def test_ranked_analysis_e2e_flow(e2e_test_setup, db_session):  # noqa: F841
    """
    Tests the full E2E flow for ranked analysis against live dependencies:
    1. Pre-analyzes procurements, creating analysis records in the DB.
    2. Injects a donation to establish a budget.
    3. Triggers the ranked analysis with auto-budget.
    4. Runs the worker to consume messages.
    5. Validates that analyses were processed and the budget ledger was updated.
    """
    print("\n--- Starting E2E test flow ---")
    target_date_str = "2025-08-23"
    ibge_code = "3550308"
    max_items_to_process = 2

    # Set environment variables for the run
    os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"
    os.environ["GCP_GEMINI_PRICE_PER_1K_TOKENS"] = "0.002"
    # Ensure a dummy zip file exists for document processing
    fixture_dir = Path(f"tests/fixtures/{ibge_code}/{target_date_str}/")
    fixture_path = fixture_dir / "Anexos.zip"
    if not fixture_path.exists():
        fixture_dir.mkdir(parents=True, exist_ok=True)
        with ZipFile(fixture_path, "w") as zf:
            zf.writestr("dummy_document.pdf", b"dummy pdf content")

    # 1. Run pre-analysis to find procurements and create analysis entries
    pre_analyze_command = (
        f"poetry run python -m source.cli pre-analyze "
        f"--start-date {target_date_str} --end-date {target_date_str} "
        f"--max-messages {max_items_to_process}"
    )
    run_command(pre_analyze_command)

    # 2. Setup database with a donation
    print("\n--- Setting up database for ranked analysis ---")
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        # Insert a donation to fund the analysis
        connection.execute(
            text(
                "INSERT INTO donations (id, donor_identifier, amount, transaction_id, created_at) "
                "VALUES (:id, :donor_identifier, :amount, :transaction_id, NOW())"
            ),
            [{"id": str(uuid.uuid4()), "donor_identifier": "E2E_TEST_DONOR", "amount": 15.00, "transaction_id": "E2E_TEST_TX_ID"}],
        )
        connection.commit()
        print("--- Inserted mock donation ---")

    # 3. Trigger ranked analysis with auto-budget
    ranked_analysis_command = (
        "poetry run python -m source.cli trigger-ranked-analysis "
        "--use-auto-budget --budget-period daily"
    )
    run_command(ranked_analysis_command)

    # 4. Run the worker to process messages
    worker_command = (
        f"poetry run python -m source.worker "
        f"--max-messages {max_items_to_process} "
        f"--timeout 5 "
        f"--max-output-tokens None"
    )
    run_command(worker_command)

    # 5. Validate data in the database
    print("\n--- Validating data in tables ---")
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))

        # Check that the expected number of analyses were successful
        completed_analyses = connection.execute(text("SELECT * FROM procurement_analyses WHERE status = 'ANALYSIS_SUCCESSFUL'")).mappings().all()
        print(f"Successfully completed analyses: {len(completed_analyses)}/{max_items_to_process}")
        assert len(completed_analyses) == max_items_to_process, f"Expected {max_items_to_process} successful analyses."

        # Check that the budget_ledgers table has the correct number of entries
        ledger_entries = connection.execute(text("SELECT * FROM budget_ledgers")).mappings().all()
        assert len(ledger_entries) == max_items_to_process, f"Expected {max_items_to_process} entries in budget_ledgers"
        print(f"--- budget_ledgers table check passed with {len(ledger_entries)} entries ---")

    print("\n--- E2E test flow completed successfully ---")

    # Final step: Dump all data from the test schema for critical analysis
    print("\n--- Critical Analysis Data Dump ---")
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        get_tables_query = text("SELECT tablename FROM pg_tables WHERE schemaname = :schema")
        tables_result = connection.execute(get_tables_query, {"schema": os.environ['POSTGRES_DB_SCHEMA']})
        table_names = [row[0] for row in tables_result if row[0] != "alembic_version"]
        if "budget_ledgers" not in table_names:
            table_names.append("budget_ledgers")
        if "donations" not in table_names:
            table_names.append("donations")

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
