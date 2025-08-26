import json
import os
import time
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from click.testing import CliRunner
from google.api_core import exceptions
from google.auth.credentials import AnonymousCredentials
from google.cloud import pubsub_v1
from models.analysis import Analysis
from sqlalchemy import create_engine, text

from source.cli.commands import analysis_command as cli_main
from source.providers.config import ConfigProvider
from source.worker.subscription import Subscription


@pytest.fixture(scope="session", autouse=True)
def db_session():
    """
    Connects to the database and creates a unique schema for the test session.
    Ensures that the database is clean before and after the tests.
    """
    # --- Create dummy fixture file if it doesn't exist ---
    fixture_dir = Path("tests/fixtures/3304557/2025-08-23/")
    fixture_path = fixture_dir / "Anexos.zip"
    if not fixture_path.exists():
        fixture_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(fixture_path, "w") as zf:
            zf.writestr("dummy_document.pdf", b"dummy pdf content")

    config = ConfigProvider.get_config()

    def get_container_ip_by_service(service_name):
        import subprocess  # nosec B404

        try:
            # Find the container ID using its docker-compose service label
            container_id_result = subprocess.run(  # nosec B603
                [
                    "/usr/bin/sudo",
                    "/usr/bin/docker",
                    "ps",
                    "-q",
                    "--filter",
                    f"label=com.docker.compose.service={service_name}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            container_id = container_id_result.stdout.strip()
            if not container_id:
                pytest.fail(f"Could not find container for service {service_name}")

            # Inspect the container using its ID to get the IP address
            inspect_result = subprocess.run(  # nosec B603
                ["/usr/bin/sudo", "/usr/bin/docker", "inspect", container_id],
                check=True,
                capture_output=True,
                text=True,
            )
            data = json.loads(inspect_result.stdout)
            # The network name might change based on the project directory name
            network_name = list(data[0]["NetworkSettings"]["Networks"].keys())[0]
            return data[0]["NetworkSettings"]["Networks"][network_name]["IPAddress"]
        except (subprocess.CalledProcessError, KeyError, IndexError) as e:
            pytest.fail(f"Could not get IP for service {service_name}: {e}")

    # Dynamically set emulator hosts
    pubsub_ip = get_container_ip_by_service("pubsub")
    gcs_ip = get_container_ip_by_service("gcs")
    os.environ["PUBSUB_EMULATOR_HOST"] = f"{pubsub_ip}:8085"
    os.environ["GCP_GCS_HOST"] = f"http://{gcs_ip}:8086"

    # Dynamically set unique schema for test isolation
    schema_name = f"test_schema_{uuid.uuid4().hex}"
    os.environ["POSTGRES_DB_SCHEMA"] = schema_name

    db_url = (
        f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}@"
        f"{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
    )
    engine = create_engine(db_url)

    try:
        with engine.connect() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            connection.commit()
            time.sleep(1)
            connection.execute(text(f"CREATE SCHEMA {schema_name}"))
            connection.commit()

        # --- Run Migrations ---
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("alembic.ini")
        # The programmatic call to alembic will use the environment variables
        # that have already been set, including POSTGRES_DB_SCHEMA
        command.upgrade(alembic_cfg, "head")

        yield  # Tests run at this point

    finally:
        # --- Teardown ---
        with engine.connect() as connection:
            connection.execute(text(f"SET search_path TO {schema_name}"))
            connection.execute(
                text("TRUNCATE procurement, procurement_analysis, file_record RESTART IDENTITY CASCADE;")
            )
            connection.commit()
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            connection.commit()
        engine.dispose()


@pytest.fixture(scope="function")
def integration_test_setup(db_session):  # noqa: F841
    """
    Creates and tears down isolated resources for a single integration test function.
    -   Unique Pub/Sub topic and subscription.
    -   Sets environment variables for the test run.
    """
    project_id = "public-detective"
    os.environ["GCP_PROJECT"] = project_id
    os.environ["GCP_GCS_BUCKET_PROCUREMENTS"] = "procurements"
    os.environ["GCP_GEMINI_API_KEY"] = "dummy-key-for-testing"

    # --- Unique Identifiers for Isolation ---
    run_id = uuid.uuid4().hex

    # Pub/Sub
    topic_name = f"procurements-topic-{run_id}"
    subscription_name = f"procurements-subscription-{run_id}"
    os.environ["GCP_PUBSUB_TOPIC_PROCUREMENTS"] = topic_name
    os.environ["GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS"] = subscription_name

    # GCS
    gcs_prefix = f"test-run-{run_id}"
    os.environ["GCP_GCS_TEST_PREFIX"] = gcs_prefix

    # --- Service Client Setup ---
    publisher = pubsub_v1.PublisherClient(credentials=AnonymousCredentials())
    subscriber = pubsub_v1.SubscriberClient(credentials=AnonymousCredentials())

    # We need a GCS client for cleanup
    from google.cloud import storage

    gcs_client = storage.Client(credentials=AnonymousCredentials(), project=project_id)

    topic_path = publisher.topic_path(project_id, topic_name)
    subscription_path = subscriber.subscription_path(project_id, subscription_name)

    try:
        # --- Resource Creation ---
        publisher.create_topic(request={"name": topic_path})
        subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})

        # Add a delay to ensure the subscription is fully propagated in the emulator
        time.sleep(5)

        yield topic_name, subscription_name

    finally:
        # --- Teardown ---
        # GCS Cleanup
        try:
            bucket = gcs_client.bucket(os.environ["GCP_GCS_BUCKET_PROCUREMENTS"])
            blobs_to_delete = list(bucket.list_blobs(prefix=gcs_prefix))
            if blobs_to_delete:
                for blob in blobs_to_delete:
                    blob.delete()
        except Exception as e:
            print(f"Error during GCS cleanup: {e}")

        # Pub/Sub Cleanup
        try:
            subscriber.delete_subscription(request={"subscription": subscription_path})
            publisher.delete_topic(request={"topic": topic_path})
        except exceptions.NotFound as e:
            print(f"Could not find topic/subscription to delete: {e}")


def load_fixture(path):
    """Loads a JSON fixture file from the specified path."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_binary_fixture(path):
    """Loads a binary fixture file from the specified path."""
    with open(path, "rb") as f:
        return f.read()


@pytest.mark.timeout(180)
def test_full_flow_integration(integration_test_setup):  # noqa: F841
    """
    Tests the full, integrated flow from CLI to Worker to Database.
    - Mocks only the external PNCP and Gemini APIs.
    - Uses real (emulated) GCS, Pub/Sub, and Postgres.
    """
    # --- 1. Setup and Fixture Loading ---
    ibge_code = "3304557"
    target_date_str = "2025-08-23"
    fixture_base_path = f"tests/fixtures/{ibge_code}/{target_date_str}"

    procurement_list_fixture = load_fixture(f"{fixture_base_path}/pncp_procurement_list.json")
    document_list_fixture = load_fixture(f"{fixture_base_path}/pncp_document_list.json")
    gemini_response_fixture = Analysis.model_validate(load_fixture(f"{fixture_base_path}/gemini_response.json"))
    attachments_fixture = load_binary_fixture(f"{fixture_base_path}/Anexos.zip")

    # The procurement that the test will focus on
    target_procurement = procurement_list_fixture[0]
    procurement_control_number = target_procurement["numeroControlePNCP"]

    # --- 2. Mock External Boundaries ---

    # We need a more sophisticated mock for requests.get to handle different URLs
    def mock_requests_get(url, **kwargs):
        mock_response = requests.Response()
        mock_response.status_code = 200

        # Mock for fetching the procurement list
        if "contratacoes/atualizacao" in url:
            mock_response.json = lambda: {
                "data": procurement_list_fixture,
                "totalPaginas": 1,
                "totalRegistros": len(procurement_list_fixture),
                "numeroPagina": 1,
            }
        elif f"compras/{target_procurement['anoCompra']}/{target_procurement['sequencialCompra']}/arquivos" in url:
            if url.endswith("/arquivos"):
                mock_response.json = lambda: document_list_fixture
            else:
                mock_response._content = attachments_fixture
                mock_response.headers["Content-Disposition"] = 'attachment; filename="Anexos.zip"'
        else:
            mock_response.status_code = 404

        return mock_response

    with (
        patch("source.repositories.procurement.requests.get", side_effect=mock_requests_get),
        patch(
            "source.services.analysis.AiProvider.get_structured_analysis",
            return_value=gemini_response_fixture,
        ),
        patch(
            "source.worker.subscription.Subscription._debug_pause",
            lambda self, prompt=None: None,
        ),
    ):

        # --- 3. Execute CLI ---
        os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"

        runner = CliRunner()
        # The CLI should now use the unique topic from the environment
        result = runner.invoke(
            cli_main,
            ["--start-date", target_date_str, "--end-date", target_date_str],
        )

        assert result.exit_code == 0, f"CLI command failed: {result.output}"
        assert "Analysis completed successfully!" in result.output

        # Add a small delay to ensure messages are available for the worker
        time.sleep(2)

        # --- 4. Execute Worker ---
        # The worker will use the unique subscription from the environment
        subscription = Subscription()
        try:
            subscription.run(max_messages=1)
        except Exception as e:
            pytest.fail(f"Worker failed with exception: {e}")
    config = ConfigProvider.get_config()
    db_url = (
        f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}@"
        f"{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
    )
    engine = create_engine(db_url)
    with engine.connect() as connection:
        connection.execute(text(f"SET search_path TO {config.POSTGRES_DB_SCHEMA}"))
        query = text(
            "SELECT risk_score, summary, document_hash FROM procurement_analysis "
            "WHERE procurement_control_number = :pcn"
        )
        db_result = connection.execute(query, {"pcn": procurement_control_number}).fetchone()

    assert db_result is not None, f"No analysis found in the database for {procurement_control_number}"

    risk_score, summary, document_hash = db_result

    # Compare with the data from our Gemini fixture
    assert risk_score == gemini_response_fixture.risk_score
    assert summary == gemini_response_fixture.summary
    assert document_hash is not None
