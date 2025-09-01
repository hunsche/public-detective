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
    # Ensure dummy zip file exists for tests that might need it
    fixture_dir = Path("tests/fixtures/3304557/2025-08-23/")
    fixture_path = fixture_dir / "Anexos.zip"
    if not fixture_path.exists():
        fixture_dir.mkdir(parents=True, exist_ok=True)
        with ZipFile(fixture_path, "w") as zf:
            zf.writestr("dummy_document.pdf", b"dummy pdf content")

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
                text("TRUNCATE procurements, procurement_analyses, file_records RESTART IDENTITY CASCADE;")
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


@pytest.mark.timeout(300)
def test_simplified_e2e_flow(e2e_test_setup, db_session):  # noqa: F841
    """
    Tests the full E2E flow against live dependencies:
    1. Pre-analyzes procurements, creating analysis records in the DB.
    2. Queries the DB for the IDs of the newly created analyses.
    3. Triggers the analysis for each ID, publishing messages to Pub/Sub.
    4. Runs the worker to consume messages and perform the analysis.
    5. Validates that the analyses were successfully completed in the DB.
    """
    print("\n--- Starting E2E test flow ---")
    target_date_str = "2025-08-23"
    ibge_code = "3550308"
    max_items_to_process = 2

    # Set environment variables for the run
    os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"
    os.environ["GCP_GEMINI_PRICE_PER_1K_TOKENS"] = "0.002"

    # 1. Run pre-analysis to find procurements and create analysis entries
    pre_analyze_command = (
        f"poetry run python -m source.cli pre-analyze "
        f"--start-date {target_date_str} --end-date {target_date_str} "
        f"--max-messages {max_items_to_process}"
    )
    run_command(pre_analyze_command)

    # 2. Query the database for the IDs of the analyses to be processed
    print("\n--- Querying database for analysis IDs ---")
    analysis_ids = []
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        result = connection.execute(
            text("SELECT analysis_id FROM procurement_analyses ORDER BY analysis_id DESC LIMIT :limit"),
            {"limit": max_items_to_process},
        )
        analysis_ids = [row[0] for row in result]
        assert len(analysis_ids) >= 1, f"Expected to find at least 1 analysis, but found {len(analysis_ids)}."
    print(f"Found analysis IDs: {analysis_ids}")

    # 3. Trigger each analysis, publishing a message to the queue
    for analysis_id in analysis_ids:
        analyze_command = f"poetry run python -m source.cli analyze --analysis-id {analysis_id}"
        run_command(analyze_command)

    # 4. Run the worker to process messages from the queue
    worker_command = f"poetry run python -m source.worker " f"--max-messages {len(analysis_ids)} " f"--timeout 5"
    run_command(worker_command)

    # 5. Validate data in the database
    print("\n--- Validating data in tables ---")
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))

        # Basic assertion: Check if all triggered analyses were successful
        completed_analysis_query = text(
            """
            SELECT
                analysis_id,
                procurement_control_number,
                version_number,
                status,
                risk_score,
                risk_score_rationale,
                procurement_summary,
                analysis_summary,
                red_flags,
                warnings,
                original_documents_gcs_path,
                processed_documents_gcs_path,
                estimated_cost,
                created_at,
                updated_at
            FROM procurement_analyses
            WHERE status = 'ANALYSIS_SUCCESSFUL' AND analysis_id = ANY(:ids)
            """
        )
        completed_analyses = connection.execute(completed_analysis_query, {"ids": analysis_ids}).mappings().all()

        print(f"Successfully completed analyses: {len(completed_analyses)}/{len(analysis_ids)}")
        assert len(completed_analyses) == len(analysis_ids), "Not all triggered analyses were successful."

        for analysis in completed_analyses:
            assert analysis["procurement_summary"] is not None
            assert analysis["analysis_summary"] is not None

        # Generic data integrity assertions
        print("\n--- Running generic data integrity checks ---")
        for analysis in completed_analyses:
            analysis_id = analysis["analysis_id"]
            print(f"Checking analysis_id: {analysis_id}")

            # Assert GCS paths are populated
            assert (
                analysis["original_documents_gcs_path"] is not None and analysis["original_documents_gcs_path"] != ""
            ), f"original_documents_gcs_path is missing for analysis {analysis_id}"
            assert (
                analysis["processed_documents_gcs_path"] is not None and analysis["processed_documents_gcs_path"] != ""
            ), f"processed_documents_gcs_path is missing for analysis {analysis_id}"

            # Assert file_records table is populated for this analysis
            file_record_query = text(
                """
                SELECT
                    id,
                    analysis_id,
                    file_name,
                    gcs_path,
                    extension,
                    size_bytes,
                    nesting_level,
                    included_in_analysis,
                    exclusion_reason,
                    prioritization_logic,
                    created_at,
                    updated_at
                FROM file_records
                WHERE analysis_id = :analysis_id
                """
            )
            file_records = connection.execute(file_record_query, {"analysis_id": analysis_id}).mappings().all()

            assert len(file_records) > 0, f"No file_records entries found for analysis {analysis_id}"
            print(f"Found {len(file_records)} file_records entries.")

            # Assert all file_records have a GCS path
            for record in file_records:
                assert (
                    record["gcs_path"] is not None and record["gcs_path"] != ""
                ), f"gcs_path is missing for file_records {record['id']}"

        print("--- Generic data integrity checks passed ---")

    print("\n--- E2E test flow completed successfully ---")

    # Final step: Dump all data from the test schema for critical analysis
    print("\n--- Critical Analysis Data Dump ---")
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        # Get all tables in the current schema
        get_tables_query = text("SELECT tablename FROM pg_tables WHERE schemaname = :schema")
        tables_result = connection.execute(get_tables_query, {"schema": os.environ["POSTGRES_DB_SCHEMA"]})
        table_names = [row[0] for row in tables_result if row[0] != "alembic_version"]

        # Dump each table's content
        for table_name in table_names:
            print(f"\n--- Dumping table: {table_name} ---")
            dump_query = text(f"SELECT * FROM {table_name}")  # nosec B608
            records = connection.execute(dump_query).mappings().all()
            if not records:
                print("[]")
            else:
                # Convert records to a JSON-serializable format
                serializable_records = [{key: str(value) for key, value in record.items()} for record in records]
                print(json.dumps(serializable_records, indent=2, ensure_ascii=False))
    print("\n--- Data Dump Complete ---")
