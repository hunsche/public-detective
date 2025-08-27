import io
import json
import os
import threading
import time
import uuid
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from click.testing import CliRunner
from google.api_core import exceptions
from google.auth.credentials import AnonymousCredentials
from google.cloud import pubsub_v1, storage
from models.analysis import Analysis
from providers.ai import AiProvider
from providers.gcs import GcsProvider
from providers.logging import LoggingProvider
from providers.pubsub import PubSubProvider
from repositories.analysis import AnalysisRepository
from repositories.file_record import FileRecordRepository
from repositories.procurement import ProcurementRepository
from services.analysis import AnalysisService
from sqlalchemy import create_engine, text

from source.cli.commands import pre_analyze_command as cli_main
from source.providers.config import ConfigProvider


@pytest.fixture(scope="session", autouse=True)
def db_session():
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
            container_id_result = subprocess.run(
                ["sudo", "-n", "docker", "ps", "-q", "--filter", f"label=com.docker.compose.service={service_name}"],
                check=True,
                capture_output=True,
                text=True,
            )  # nosec B603, B607
            container_id = container_id_result.stdout.strip()
            if not container_id:
                pytest.fail(f"Could not find container for service {service_name}")
            inspect_result = subprocess.run(
                ["sudo", "-n", "docker", "inspect", container_id], check=True, capture_output=True, text=True
            )  # nosec B603, B607
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
            connection.execute(text("DROP TYPE IF EXISTS analysis_status CASCADE;"))
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            connection.commit()
            time.sleep(1)
            connection.execute(text(f"CREATE SCHEMA {schema_name}"))
            connection.commit()
            connection.execute(text(f"SET search_path TO {schema_name}"))
            connection.commit()
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")

        with engine.connect() as connection:
            connection.execute(text(f"SET search_path TO {schema_name}"))
            connection.execute(
                text("TRUNCATE procurement, procurement_analysis, file_record RESTART IDENTITY CASCADE;")
            )
            connection.commit()
        yield engine
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
        logger = LoggingProvider().get_logger()
        try:
            bucket = gcs_client.bucket(os.environ["GCP_GCS_BUCKET_PROCUREMENTS"])
            blobs_to_delete = list(bucket.list_blobs(prefix=gcs_prefix))
            for blob in blobs_to_delete:
                blob.delete()
        except Exception as e:
            logger.info(f"Ignoring GCS teardown error (expected with anonymous creds): {e}")
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


@pytest.mark.timeout(180)
def test_full_flow_integration(integration_test_setup, db_session):  # noqa: F841
    ibge_code = "3304557"
    target_date_str = "2025-08-23"
    fixture_base_path = f"tests/fixtures/{ibge_code}/{target_date_str}"
    procurement_list_fixture = load_fixture(f"{fixture_base_path}/pncp_procurement_list.json")
    document_list_fixture = load_fixture(f"{fixture_base_path}/pncp_document_list.json")
    attachments_fixture = load_binary_fixture(f"{fixture_base_path}/Anexos.zip")

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
        elif url.endswith("/arquivos"):
            mock_response.json = lambda: document_list_fixture
        elif "/arquivos/" in url:
            mock_response._content = attachments_fixture
            mock_response.headers["Content-Disposition"] = 'attachment; filename="Anexos.zip"'
        else:
            mock_response.status_code = 404
        return mock_response

    db_engine = db_session
    with patch("source.repositories.procurement.requests.get", side_effect=mock_requests_get), patch(
        "source.providers.ai.AiProvider.count_tokens_for_analysis", return_value=10000
    ):
        os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"
        runner = CliRunner()
        result = runner.invoke(cli_main, ["--start-date", target_date_str, "--end-date", target_date_str])
        assert result.exit_code == 0, f"CLI command failed: {result.output}"
        assert "Pre-analysis completed successfully!" in result.output

    with db_engine.connect() as connection:
        num_procurements = len(procurement_list_fixture)
        total_query = text("SELECT COUNT(*) FROM procurement_analysis")
        analysis_count = connection.execute(total_query).scalar_one()
        assert (
            analysis_count == num_procurements
        ), f"Expected {num_procurements} pre-analyses, but found {analysis_count} in the database."

        target_procurement = procurement_list_fixture[0]
        pcn = target_procurement["numeroControlePNCP"]
        specific_query = text(
            "SELECT status, estimated_cost FROM procurement_analysis WHERE " "procurement_control_number = :pcn"
        )
        db_result = connection.execute(specific_query, {"pcn": pcn}).fetchone()

        assert db_result is not None, f"No pre-analysis found in the database for {pcn}"
        status, estimated_cost = db_result
        assert status == "PENDING_ANALYSIS"
        assert estimated_cost is not None
        assert estimated_cost > 0
