import json
import os
import threading
import time
import uuid
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from click.testing import CliRunner
from google.api_core import exceptions
from google.auth.credentials import AnonymousCredentials
from google.cloud import pubsub_v1, storage
from models.analysis import Analysis
from providers.ai import AiProvider
from providers.database import DatabaseManager
from providers.gcs import GcsProvider
from providers.pubsub import PubSubProvider
from repositories.analysis import AnalysisRepository
from repositories.file_record import FileRecordRepository
from repositories.procurement import ProcurementRepository
from services.analysis import AnalysisService
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
    fixture_dir = Path("tests/fixtures/3304557/2025-08-23/")
    fixture_path = fixture_dir / "Anexos.zip"
    if not fixture_path.exists():
        fixture_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(fixture_path, "w") as zf:
            zf.writestr("dummy_document.pdf", b"dummy pdf content")

    config = ConfigProvider.get_config()

    def get_container_ip_by_service(service_name):
        # nosec B404
        import subprocess

        try:
            # nosec B603, B607
            container_id_result = subprocess.run(
                ["sudo", "-n", "docker", "ps", "-q", "--filter", f"label=com.docker.compose.service={service_name}"],
                check=True,
                capture_output=True,
                text=True,
            )
            container_id = container_id_result.stdout.strip()
            if not container_id:
                pytest.fail(f"Could not find container for service {service_name}")

            # nosec B603, B607
            inspect_result = subprocess.run(
                ["sudo", "-n", "docker", "inspect", container_id], check=True, capture_output=True, text=True
            )
            data = json.loads(inspect_result.stdout)
            network_name = list(data[0]["NetworkSettings"]["Networks"].keys())[0]
            return data[0]["NetworkSettings"]["Networks"][network_name]["IPAddress"]
        except (subprocess.CalledProcessError, KeyError, IndexError) as e:
            pytest.fail(f"Could not get IP for service {service_name}: {e}")

    pubsub_ip = get_container_ip_by_service("pubsub")
    gcs_ip = get_container_ip_by_service("gcs")
    os.environ["PUBSUB_EMULATOR_HOST"] = f"{pubsub_ip}:8085"
    os.environ["GCP_GCS_HOST"] = f"http://{gcs_ip}:8086"

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

        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")

        yield

    finally:
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
    project_id = "public-detective"
    os.environ["GCP_PROJECT"] = project_id
    os.environ["GCP_GCS_BUCKET_PROCUREMENTS"] = "procurements"
    os.environ["GCP_GEMINI_API_KEY"] = "dummy-key-for-testing"

    run_id = uuid.uuid4().hex
    topic_name = f"procurements-topic-{run_id}"
    subscription_name = f"procurements-subscription-{run_id}"
    os.environ["GCP_PUBSUB_TOPIC_PROCUREMENTS"] = topic_name
    os.environ["GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS"] = subscription_name
    gcs_prefix = f"test-run-{run_id}"
    os.environ["GCP_GCS_TEST_PREFIX"] = gcs_prefix

    publisher = pubsub_v1.PublisherClient(credentials=AnonymousCredentials())
    subscriber = pubsub_v1.SubscriberClient(credentials=AnonymousCredentials())
    gcs_client = storage.Client(credentials=AnonymousCredentials(), project=project_id)
    topic_path = publisher.topic_path(project_id, topic_name)
    subscription_path = subscriber.subscription_path(project_id, subscription_name)

    try:
        publisher.create_topic(request={"name": topic_path})
        subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})
        yield
    finally:
        try:
            bucket = gcs_client.bucket(os.environ["GCP_GCS_BUCKET_PROCUREMENTS"])
            blobs_to_delete = list(bucket.list_blobs(prefix=gcs_prefix))
            for blob in blobs_to_delete:
                blob.delete()
        except Exception as e:
            # Best-effort cleanup, ignore errors during teardown
            print(f"Ignoring GCS teardown error: {e}")
        try:
            subscriber.delete_subscription(request={"subscription": subscription_path})
            publisher.delete_topic(request={"topic": topic_path})
        except exceptions.NotFound:
            pass


def load_fixture(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_binary_fixture(path):
    with open(path, "rb") as f:
        return f.read()


def wait_for_analysis_in_db(pcn: str, timeout: int = 120):
    config = ConfigProvider.get_config()
    db_url = (
        f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}@"
        f"{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
    )
    engine = create_engine(db_url)
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        with engine.connect() as connection:
            connection.execute(text(f"SET search_path TO {config.POSTGRES_DB_SCHEMA}"))
            query = text(
                "SELECT risk_score, summary, document_hash "
                "FROM procurement_analysis "
                "WHERE procurement_control_number = :pcn"
            )
            result = connection.execute(query, {"pcn": pcn}).fetchone()
            if result:
                return result
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for analysis of PCN {pcn} in the database.")


@pytest.mark.timeout(180)
def test_full_flow_integration(integration_test_setup):  # noqa: F841
    ibge_code = "3304557"
    target_date_str = "2025-08-23"
    fixture_base_path = f"tests/fixtures/{ibge_code}/{target_date_str}"
    procurement_list_fixture = load_fixture(f"{fixture_base_path}/pncp_procurement_list.json")
    document_list_fixture = load_fixture(f"{fixture_base_path}/pncp_document_list.json")
    gemini_response_fixture = Analysis.model_validate(load_fixture(f"{fixture_base_path}/gemini_response.json"))
    attachments_fixture = load_binary_fixture(f"{fixture_base_path}/Anexos.zip")
    target_procurement = procurement_list_fixture[0]
    procurement_control_number = target_procurement["numeroControlePNCP"]

    def mock_requests_get(url, **kwargs):
        mock_response = requests.Response()
        mock_response.status_code = 200
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

    # This test is now a Composition Root for the worker part of the flow.
    db_engine = DatabaseManager.get_engine()
    pubsub_provider = PubSubProvider()
    gcs_provider = GcsProvider()
    # The AI provider is mocked
    ai_provider = MagicMock(spec=AiProvider)
    ai_provider.get_structured_analysis.return_value = gemini_response_fixture

    analysis_repo = AnalysisRepository(engine=db_engine)
    file_record_repo = FileRecordRepository(engine=db_engine)
    procurement_repo = ProcurementRepository(engine=db_engine, pubsub_provider=pubsub_provider)

    analysis_service = AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        file_record_repo=file_record_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
    )

    with patch("source.repositories.procurement.requests.get", side_effect=mock_requests_get):
        os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"
        runner = CliRunner()
        result = runner.invoke(cli_main, ["--start-date", target_date_str, "--end-date", target_date_str])
        assert result.exit_code == 0, f"CLI command failed: {result.output}"
        assert "Analysis completed successfully!" in result.output

        # Inject the fully composed, real service into the worker
        subscription = Subscription(analysis_service=analysis_service)
        # Ensure debug mode is off for this test to prevent hanging on input()
        subscription.config.IS_DEBUG_MODE = False
        worker_thread = threading.Thread(target=lambda: subscription.run(max_messages=1), daemon=True)
        worker_thread.start()

        db_result = wait_for_analysis_in_db(procurement_control_number)

    assert db_result is not None, f"No analysis found in the database for {procurement_control_number}"
    risk_score, summary, document_hash = db_result
    assert risk_score == gemini_response_fixture.risk_score
    assert summary == gemini_response_fixture.summary
    assert document_hash is not None
