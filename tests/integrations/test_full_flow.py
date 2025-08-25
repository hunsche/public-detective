import json
import os
import time
import uuid
from unittest.mock import patch

import pytest
import requests
from click.testing import CliRunner
from google.api_core import exceptions
from google.cloud import pubsub_v1
from models.analysis import Analysis
from sqlalchemy import create_engine, text

from source.cli.commands import analysis_command as cli_main
from source.worker.subscription import Subscription


@pytest.fixture(scope="session", autouse=True)
def docker_services_session():
    """
    Starts and stops the docker-compose services once for the entire test session.
    Ensures all containers are ready before any tests run.
    """
    # Use a unique project name to avoid conflicts in CI environments
    project_name = f"publicdetective-test-{uuid.uuid4().hex[:8]}"
    os.environ["COMPOSE_PROJECT_NAME"] = project_name

    # Check if docker is installed and running
    import subprocess  # nosec B404

    try:
        subprocess.run(["sudo", "docker", "info"], check=True, capture_output=True)  # nosec B603, B607
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker is not running or not installed. Skipping integration tests.")

    print("Starting Docker services for the test session...")
    subprocess.run(["sudo", "docker", "compose", "up", "-d"], check=True)  # nosec B603, B607

    # --- Get Dynamic Ports ---
    def get_service_port(service_name, internal_port):
        try:
            command = ["sudo", "docker", "compose", "port", service_name, str(internal_port)]
            result = subprocess.run(  # nosec B603
                command,
                check=True,
                capture_output=True,
                text=True,
            )
            # Output is typically in the format '0.0.0.0:PORT' or '::1:PORT'
            return result.stdout.strip().split(":")[-1]
        except subprocess.CalledProcessError as e:
            print(f"Could not get port for {service_name}:{internal_port}. Error: {e.stderr}")
            pytest.fail(f"Failed to get dynamic port for {service_name}.")

    postgres_port = get_service_port("postgres-test", 5432)
    pubsub_port = get_service_port("pubsub", 8085)
    gcs_port = get_service_port("gcs", 8086)

    print(f"Postgres-test running on port: {postgres_port}")
    print(f"Pub/Sub emulator running on port: {pubsub_port}")
    print(f"GCS emulator running on port: {gcs_port}")

    # Set environment variables for the entire session
    os.environ["POSTGRES_HOST"] = "localhost"
    os.environ["POSTGRES_PORT"] = postgres_port
    os.environ["POSTGRES_DB"] = "public_detective_test"
    os.environ["POSTGRES_USER"] = "postgres"
    os.environ["POSTGRES_PASSWORD"] = "postgres"  # nosec B105
    os.environ["PUBSUB_EMULATOR_HOST"] = f"localhost:{pubsub_port}"
    os.environ["GCP_GCS_HOST"] = f"http://localhost:{gcs_port}"

    print("Waiting for services to become healthy...")
    time.sleep(10)

    print("Applying database migrations...")
    migration_result = subprocess.run(
        ["poetry", "run", "alembic", "upgrade", "head"], check=False, capture_output=True
    )  # nosec B603, B607
    if migration_result.returncode != 0:
        print("Alembic migration failed!")
        print(migration_result.stdout.decode())
        print(migration_result.stderr.decode())
        subprocess.run(
            ["sudo", "docker", "compose", "-p", project_name, "down", "-v", "--remove-orphans"], check=True
        )  # nosec B603, B607
        pytest.fail("Database migration failed, aborting tests.")

    yield

    print("Stopping Docker services for the test session...")
    subprocess.run(
        ["sudo", "docker", "compose", "-p", project_name, "down", "-v", "--remove-orphans"], check=True
    )  # nosec B603, B607


@pytest.fixture(scope="function")
def integration_test_setup(docker_services_session):  # noqa: F841
    """
    Creates and tears down isolated resources for a single integration test function.
    -   Unique Pub/Sub topic and subscription.
    -   Sets environment variables for the test run.
    """
    project_id = "public-detective-test"
    os.environ["GCP_PROJECT"] = project_id
    os.environ["GCP_GCS_BUCKET_PROCUREMENTS"] = "procurements"
    os.environ["GCP_GEMINI_API_KEY"] = "dummy-key-for-testing"

    # --- Unique Topic/Subscription ---
    run_id = uuid.uuid4().hex
    topic_name = f"procurements-topic-{run_id}"
    subscription_name = f"procurements-subscription-{run_id}"
    os.environ["GCP_PUBSUB_TOPIC_PROCUREMENTS"] = topic_name
    os.environ["GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS"] = subscription_name

    # Create Topic and Subscription
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    topic_path = publisher.topic_path(project_id, topic_name)
    subscription_path = subscriber.subscription_path(project_id, subscription_name)

    try:
        publisher.create_topic(request={"name": topic_path})
        print(f"Created Pub/Sub topic: {topic_path}")
        subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})
        print(f"Created Pub/Sub subscription: {subscription_path}")

        # Add a delay to ensure the subscription is fully propagated in the emulator
        time.sleep(5)

    except exceptions.AlreadyExists:
        print("Topic/Subscription already exist, which is unexpected in a clean test run.")
        pass  # Should not happen with unique names

    yield topic_name, subscription_name

    # --- Teardown ---
    print("Tearing down test resources...")
    try:
        subscriber.delete_subscription(request={"subscription": subscription_path})
        print(f"Deleted subscription: {subscription_path}")
        publisher.delete_topic(request={"topic": topic_path})
        print(f"Deleted topic: {topic_path}")
    except exceptions.NotFound:
        print("Could not find topic/subscription to delete. They may have been cleaned up already.")


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
            print(f"Mocked PNCP procurement list URL: {url}")
            # Mock for fetching the document list for a specific procurement
        elif f"compras/{target_procurement['anoCompra']}/{target_procurement['sequencialCompra']}/arquivos" in url:
            # Differentiate between listing documents and downloading a single file
            if url.endswith("/arquivos"):
                mock_response.json = lambda: document_list_fixture
                print(f"Mocked PNCP document list URL: {url}")
            else:
                mock_response._content = attachments_fixture
                print(f"Mocked PNCP document download URL: {url}")
        else:
            mock_response.status_code = 404
            print(f"Unhandled URL in mock_requests_get: {url}")

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
        print("Running CLI command...")

        os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"

        runner = CliRunner()
        # The CLI should now use the unique topic from the environment
        result = runner.invoke(
            cli_main,
            ["--start-date", target_date_str, "--end-date", target_date_str],
        )

        assert result.exit_code == 0, f"CLI command failed: {result.output}"
        assert "Analysis completed successfully!" in result.output
        print("CLI command finished successfully.")

        # Add a small delay to ensure messages are available for the worker
        time.sleep(2)

        # --- 4. Execute Worker ---
        print("Running Worker...")
        # The worker will use the unique subscription from the environment
        subscription = Subscription()
        subscription.run(max_messages=1)
        print("Worker finished processing.")
    print("Verifying results in the database...")
    db_url = (
        f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ['POSTGRES_HOST']}:{os.environ['POSTGRES_PORT']}/{os.environ['POSTGRES_DB']}"
    )
    engine = create_engine(db_url)
    with engine.connect() as connection:
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
    assert document_hash is not None  # Verify a hash was calculated and stored

    print("Database verification successful!")
    print(f"Found analysis for {procurement_control_number} with risk score {risk_score}.")
