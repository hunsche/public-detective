import os
import subprocess  # nosec B404
import time
import uuid
import zipfile
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from google.api_core import exceptions
from google.cloud import pubsub_v1, storage
from providers.config import ConfigProvider
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def run_command(command: str) -> None:
    """Executes a shell command and streams its output in real-time.

    Args:
        command: The shell command to execute.
    """
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


@pytest.fixture(scope="function")
def db_session() -> Generator:
    fixture_dir = Path("tests/fixtures/3304557/2025-08-23/")
    fixture_path = fixture_dir / "Anexos.zip"
    if not fixture_path.exists():
        fixture_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(fixture_path, "w") as zf:
            zf.writestr("dummy_document.pdf", b"dummy pdf content")

    config = ConfigProvider.get_config()

    # Use localhost for services, as docker-compose exposes the ports to the host
    host = "localhost"
    os.environ["POSTGRES_HOST"] = host
    os.environ["PUBSUB_EMULATOR_HOST"] = f"{host}:8085"
    os.environ["GCP_GCS_HOST"] = f"http://{host}:8086"

    schema_name = f"test_schema_{uuid.uuid4().hex}"
    os.environ["POSTGRES_DB_SCHEMA"] = schema_name
    db_url = (
        f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}@"
        f"{host}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
    )
    engine = create_engine(db_url, connect_args={"options": f"-csearch_path={schema_name}"})

    # Wait for the database to be ready before proceeding
    for _ in range(30):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            break
        except Exception:
            time.sleep(1)
    else:
        pytest.fail("Database did not become available in time.")

    try:
        with engine.connect() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            connection.commit()
            connection.execute(text(f"CREATE SCHEMA {schema_name}"))
            connection.commit()
            connection.execute(text(f"SET search_path TO {schema_name}"))
            connection.commit()

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")

        with engine.connect() as connection:
            connection.execute(text(f"SET search_path TO {schema_name}"))
            truncate_sql = text(
                "TRUNCATE procurements, procurement_analyses, file_records, "
                "procurement_analysis_status_history RESTART IDENTITY CASCADE;"
            )
            connection.execute(truncate_sql)
            connection.commit()
        yield engine
    finally:
        with engine.connect() as connection:
            connection.execute(text(f"SET search_path TO {schema_name}"))
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            connection.commit()
        engine.dispose()


@pytest.fixture(scope="function")
def e2e_environment(db_session: Engine) -> Generator:
    """Configures the environment for a single E2E test function.

    Sets up unique Pub/Sub topics, GCS paths, and cleans up afterwards.
    This fixture ensures that GCS and AI tests run against real GCP services
    by clearing emulator hosts, while Pub/Sub can still use an emulator.
    It relies on pytest-dotenv to load `GCP_SERVICE_ACCOUNT_CREDENTIALS` from the .env file.

    Args:
        db_session: The SQLAlchemy engine instance from the db_session fixture.

    Yields:
        A tuple containing the PublisherClient and the topic path.
    """
    # Ensure E2E tests for GCS and AI run against real GCP services
    os.environ.pop("GCP_GCS_HOST", None)
    os.environ.pop("GCP_AI_HOST", None)

    print("\n--- Setting up E2E test environment ---")
    project_id = os.environ.get("GCP_PROJECT", "total-entity-463718-k1")
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

    # Create a temporary credentials file for ADC
    credentials_json = os.environ.get("GCP_SERVICE_ACCOUNT_CREDENTIALS")
    if not credentials_json:
        pytest.fail("GCP_SERVICE_ACCOUNT_CREDENTIALS must be set in the environment for E2E tests.")

    temp_credentials_path = Path(f"tests/.tmp/temp_credentials_{run_id}.json")
    temp_credentials_path.parent.mkdir(parents=True, exist_ok=True)
    temp_credentials_path.write_text(credentials_json)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(temp_credentials_path)

    # Pub/Sub setup (can use emulator)
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    topic_path = publisher.topic_path(project_id, topic_name)
    subscription_path = subscriber.subscription_path(project_id, subscription_name)

    # GCS setup (uses credentials from environment loaded by pytest-dotenv)
    gcs_client = storage.Client(project=project_id)
    bucket = gcs_client.bucket(bucket_name_for_tests)

    if not bucket.exists():
        pytest.fail(f"GCS bucket '{bucket_name_for_tests}' does not exist. Please create it before running E2E tests.")

    # Teardown previous run's resources if they exist
    for blob in bucket.list_blobs(prefix=os.environ["GCP_GCS_TEST_PREFIX"]):
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

        yield publisher, topic_path

    finally:
        if temp_credentials_path.exists():
            temp_credentials_path.unlink()
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
            print(f"Clearing GCS objects in bucket: {bucket_name_for_tests}")
            for blob in bucket.list_blobs(prefix=os.environ["GCP_GCS_TEST_PREFIX"]):
                blob.delete()
            print(f"Cleared bucket: {bucket_name_for_tests}")
        except exceptions.NotFound:
            print(f"Bucket not found, skipping cleanup: {bucket_name_for_tests}")

        print("E2E test environment torn down.")
