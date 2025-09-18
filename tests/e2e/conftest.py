import os
import subprocess  # nosec B404
import tempfile
import time
import uuid
import zipfile
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from filelock import FileLock
from google.api_core import exceptions
from google.cloud.pubsub_v1 import PublisherClient, SubscriberClient
from google.cloud.storage import Client
from public_detective.providers.config import ConfigProvider
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def run_command(command_str: str) -> None:
    """Executes a shell command and streams its output in real-time.

    Args:
        command_str: The shell command to execute.
    """
    print(f"\n--- Running command: {command_str} ---")
    process = subprocess.Popen(
        command_str,
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
        pytest.fail(f"Command failed with exit code {process.returncode}: {command_str}")
    print(f"--- Command finished: {command_str} ---")


@pytest.fixture(scope="function")
def e2e_pubsub() -> Generator[tuple[PublisherClient, str], None, None]:
    """Sets up and tears down the Pub/Sub resources for an E2E test."""
    config = ConfigProvider.get_config()
    project_id = config.GCP_PROJECT
    run_id = uuid.uuid4().hex[:8]
    topic_name = f"test-topic-{run_id}"
    subscription_name = f"test-subscription-{run_id}"

    os.environ["GCP_PUBSUB_TOPIC_PROCUREMENTS"] = topic_name
    os.environ["GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS"] = subscription_name

    publisher = PublisherClient()
    subscriber = SubscriberClient()
    topic_path = publisher.topic_path(project_id, topic_name)
    subscription_path = subscriber.subscription_path(project_id, subscription_name)

    try:
        publisher.create_topic(request={"name": topic_path})
        subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})
        yield publisher, topic_path
    finally:
        try:
            subscriber.delete_subscription(request={"subscription": subscription_path})
        except exceptions.NotFound:
            pass
        try:
            publisher.delete_topic(request={"topic": topic_path})
        except exceptions.NotFound:
            pass


@pytest.fixture(scope="function")
def db_session() -> Generator[Engine, None, None]:
    """Configures a fully isolated environment for a single E2E test function.

    This comprehensive fixture handles:
    1.  **Configuration**: Sets environment variables for databases, emulators, and GCP services.
    2.  **Database**: Creates a unique, temporary PostgreSQL schema and applies all migrations.
    3.  **GCP Credentials**: Creates a temporary credentials file to ensure ADC uses the
        correct service account for the test run.
    4.  **Pub/Sub**: Creates a unique topic and subscription for the test run.
    5.  **GCS**: Cleans up any previous test run artifacts from the target bucket.
    6.  **Teardown**: Reliably tears down all created resources (DB schema, Pub/Sub topic,
        subscription, and temporary credential files) after the test completes.

    Yields:
        A tuple containing the configured PublisherClient and the full topic path.
    """
    # --- 1. Configuration and Environment Setup ---
    config = ConfigProvider.get_config()
    project_id = config.GCP_PROJECT
    bucket_name = config.GCP_GCS_BUCKET_PROCUREMENTS
    host = config.POSTGRES_HOST

    run_id = uuid.uuid4().hex[:8]
    schema_name = f"test_schema_{run_id}"
    topic_name = f"test-topic-{run_id}"
    subscription_name = f"test-subscription-{run_id}"
    gcs_test_prefix = f"test-run-{run_id}"

    # Set env vars for the test session
    os.environ["POSTGRES_HOST"] = host
    os.environ["PUBSUB_EMULATOR_HOST"] = f"{host}:8085"
    os.environ["POSTGRES_DB_SCHEMA"] = schema_name
    os.environ["GCP_GCS_BUCKET_PROCUREMENTS"] = bucket_name
    os.environ["GCP_PUBSUB_TOPIC_PROCUREMENTS"] = topic_name
    os.environ["GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS"] = subscription_name
    os.environ["GCP_GCS_TEST_PREFIX"] = gcs_test_prefix

    # Pop emulator hosts for services that should hit live GCP APIs
    os.environ.pop("GCP_GCS_HOST", None)
    os.environ.pop("GCP_GEMINI_HOST", None)

    # --- 2. Temporary ADC Credentials Setup ---
    original_credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    credentials_json = os.environ.get("GCP_SERVICE_ACCOUNT_CREDENTIALS")
    if not credentials_json:
        pytest.fail("GCP_SERVICE_ACCOUNT_CREDENTIALS must be set for E2E tests.")

    temp_credentials_path = Path(f"tests/.tmp/temp_credentials_{run_id}.json")
    temp_credentials_path.parent.mkdir(parents=True, exist_ok=True)
    temp_credentials_path.write_text(credentials_json)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(temp_credentials_path)

    # --- 3. Database Setup ---
    db_url = (
        f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}@"
        f"{host}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
    )
    engine = create_engine(db_url, connect_args={"options": f"-csearch_path={schema_name}"})

    # Wait for DB to be ready
    for _ in range(30):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            break
        except Exception:
            time.sleep(1)
    else:
        pytest.fail("Database did not become available in time.")

    # --- 4. GCP Client Initialization ---
    publisher = PublisherClient()
    subscriber = SubscriberClient()
    topic_path = publisher.topic_path(project_id, topic_name)
    subscription_path = subscriber.subscription_path(project_id, subscription_name)
    gcs_client = Client(project=project_id)
    bucket = gcs_client.bucket(bucket_name)

    if not bucket.exists():
        pytest.fail(f"GCS bucket '{bucket_name}' does not exist.")

    # --- 5. Resource Creation and Cleanup ---
    with engine.connect() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema_name}"))
        connection.commit()

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    lock_path = Path(tempfile.gettempdir()) / "e2e_alembic.lock"
    try:
        with FileLock(str(lock_path)):
            command.upgrade(alembic_cfg, "head")
    except Exception as e:
        pytest.fail(f"Alembic upgrade failed: {e}")

    # Clean up any artifacts from previous runs
    for blob in bucket.list_blobs(prefix=gcs_test_prefix):
        blob.delete()

    try:
        publisher.create_topic(request={"name": topic_path})
        subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})

        # Create a dummy zip file for tests that need it
        fixture_dir = Path("tests/fixtures/3304557/2025-08-23/")
        fixture_path = fixture_dir / "Anexos.zip"
        if not fixture_path.exists():
            fixture_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(fixture_path, "w") as zf:
                zf.writestr("dummy_document.pdf", b"dummy pdf content")

        yield engine

    finally:
        # --- 6. Teardown ---
        print("\n--- Tearing down E2E test environment ---")
        if temp_credentials_path.exists():
            temp_credentials_path.unlink()

        # Restore original credentials environment variable
        if original_credentials is None:
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        else:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = original_credentials

        try:
            for blob in bucket.list_blobs(prefix=gcs_test_prefix):
                blob.delete()
        except exceptions.NotFound:
            pass

        with engine.connect() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            connection.commit()
        engine.dispose()
        print("E2E test environment torn down.")
