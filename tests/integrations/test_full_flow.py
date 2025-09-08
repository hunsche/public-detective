import io
import json
import os
import threading
import uuid
from collections.abc import Generator
from contextlib import redirect_stdout
from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
from public_detective.cli.__main__ import cli
from click.testing import CliRunner
from google.api_core import exceptions
from google.auth.credentials import AnonymousCredentials
from google.cloud import pubsub_v1, storage
from public_detective.models.analyses import Analysis
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.models.procurements import Procurement
from public_detective.providers.ai import AiProvider
from public_detective.providers.gcs import GcsProvider
from public_detective.providers.logging import LoggingProvider
from public_detective.providers.pubsub import PubSubProvider
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.repositories.budget_ledger import BudgetLedgerRepository
from public_detective.repositories.file_records import FileRecordsRepository
from public_detective.repositories.procurements import ProcurementsRepository
from public_detective.repositories.status_history import StatusHistoryRepository
from public_detective.services.analysis import AnalysisService
from sqlalchemy import text
from sqlalchemy.engine import Engine
from public_detective.worker.subscription import Subscription


@pytest.fixture(scope="function")
def integration_test_setup(db_session: Engine) -> Generator[None, None, None]:  # noqa: F841
    project_id = "public-detective"
    os.environ["GCP_PROJECT"] = project_id
    os.environ["GCP_GCS_BUCKET_PROCUREMENTS"] = "procurements"
    
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
    # Truncate tables before each test run
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        connection.execute(text("TRUNCATE procurements, procurement_analyses, file_records RESTART IDENTITY CASCADE;"))
        connection.commit()
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
        with db_session.connect() as connection:
            connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
            connection.execute(
                text("TRUNCATE procurements, procurement_analyses, file_records RESTART IDENTITY CASCADE;")
            )
            connection.commit()


def load_fixture(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_binary_fixture(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


@pytest.mark.timeout(180)
def test_full_flow_integration(integration_test_setup: None, db_session: Engine) -> None:  # noqa: F841
    # ... setup fixtures ...
    ibge_code = "3304557"
    target_date_str = "2025-08-23"
    fixture_base_path = f"tests/fixtures/{ibge_code}/{target_date_str}"
    procurement_list_fixture = load_fixture(f"{fixture_base_path}/pncp_procurement_list.json")
    gemini_response_fixture = Analysis.model_validate(load_fixture(f"{fixture_base_path}/gemini_response.json"))

    # Set environment variables BEFORE instantiating components
    os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"
    os.environ["GCP_GEMINI_PRICE_PER_1K_TOKENS"] = "0.002"

    db_engine = db_session
    pubsub_provider = PubSubProvider()
    gcs_provider = GcsProvider()
    ai_provider = AiProvider(Analysis)
    analysis_repo = AnalysisRepository(engine=db_engine)
    file_record_repo = FileRecordsRepository(engine=db_engine)
    procurement_repo = ProcurementsRepository(engine=db_engine, pubsub_provider=pubsub_provider)
    status_history_repo = StatusHistoryRepository(engine=db_engine)
    budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)
    analysis_service = AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        file_record_repo=file_record_repo,
        status_history_repo=status_history_repo,
        budget_ledger_repo=budget_ledger_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
        pubsub_provider=pubsub_provider,
    )

    # 1. Manually insert data
    procurement_to_analyze = Procurement.model_validate(procurement_list_fixture[0])
    procurement_repo.save_procurement_version(
        procurement=procurement_to_analyze,
        raw_data=json.dumps(procurement_list_fixture[0]),
        version_number=1,
        content_hash="test-hash-1",
    )
    analysis_id = analysis_repo.save_pre_analysis(
        procurement_control_number=procurement_to_analyze.pncp_control_number,
        version_number=1,
        document_hash="pre-analysis-hash-1",
        input_tokens_used=0,
        output_tokens_used=0,
    )
    status_history_repo.create_record(
        analysis_id, ProcurementAnalysisStatus.PENDING_ANALYSIS, "Initial pre-analysis record."
    )

    # 2. Run analyze command
    with patch.object(ai_provider, "get_structured_analysis", return_value=(gemini_response_fixture, 100, 50)):
        with patch.object(procurement_repo, "process_procurement_documents", return_value=[("doc.pdf", b"content")]):
            runner = CliRunner()
            result = runner.invoke(cli, ["analyze", f"--analysis-id={analysis_id}"])
            assert result.exit_code == 0, f"CLI command failed: {result.output}"
            assert "Analysis triggered successfully!" in result.output

            # 3. Run worker
            log_capture_stream = io.StringIO()
            processing_complete_event = threading.Event()
            subscription = Subscription(
                analysis_service=analysis_service,
                processing_complete_event=processing_complete_event,
            )
            subscription.config.IS_DEBUG_MODE = False

            def worker_target() -> None:
                with redirect_stdout(log_capture_stream):
                    subscription.run(max_messages=1)

            worker_thread = threading.Thread(target=worker_target, daemon=True)
            worker_thread.start()

            event_was_set = processing_complete_event.wait(timeout=60)
            if not event_was_set:
                pytest.fail(
                    "Worker thread timed out waiting for message processing to complete.\n"
                    f"Logs:\n{log_capture_stream.getvalue()}"
                )
            worker_thread.join(timeout=5)  # Give the thread a moment to shut down
            if worker_thread.is_alive():
                pytest.fail("Worker thread did not shut down gracefully after processing.")

    # 4. Check results
    with db_engine.connect() as connection:
        analysis_query = text("SELECT status, risk_score FROM procurement_analyses WHERE analysis_id = :analysis_id")
        db_analysis = connection.execute(analysis_query, {"analysis_id": analysis_id}).fetchone()
        assert db_analysis is not None
        status, risk_score = db_analysis
        assert status == "ANALYSIS_SUCCESSFUL"
        assert risk_score == gemini_response_fixture.risk_score

        # Check history records
        history_query = text(
            "SELECT status FROM procurement_analysis_status_history "
            "WHERE analysis_id = :analysis_id ORDER BY created_at"
        )
        history_records = connection.execute(history_query, {"analysis_id": analysis_id}).fetchall()
        statuses = [record[0] for record in history_records]
        assert "PENDING_ANALYSIS" in statuses
        assert "ANALYSIS_IN_PROGRESS" in statuses
        assert "ANALYSIS_SUCCESSFUL" in statuses


@pytest.mark.timeout(180)
def test_pre_analysis_flow_integration(integration_test_setup: None, db_session: Engine) -> None:  # noqa: F841
    ibge_code = "3304557"
    target_date_str = "2025-08-23"
    fixture_base_path = f"tests/fixtures/{ibge_code}/{target_date_str}"
    procurement_list_fixture = load_fixture(f"{fixture_base_path}/pncp_procurement_list.json")
    document_list_fixture = load_fixture(f"{fixture_base_path}/pncp_document_list.json")
    attachments_fixture = load_binary_fixture(f"{fixture_base_path}/Anexos.zip")

    def mock_requests_get(url: str, **kwargs: Any) -> requests.Response:  # noqa: F841
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        if "contratacoes/atualizacao" in url:
            mock_response.json.return_value = {
                "data": procurement_list_fixture,
                "totalPaginas": 1,
                "totalRegistros": len(procurement_list_fixture),
                "numeroPagina": 1,
            }
        elif url.endswith("/arquivos"):
            mock_response.json.return_value = document_list_fixture
        elif "/arquivos/" in url:
            mock_response.content = attachments_fixture
            mock_response.headers = {"Content-Disposition": 'attachment; filename="Anexos.zip"'}
        else:
            mock_response.status_code = 404
        return mock_response

    db_engine = db_session
    pubsub_provider = PubSubProvider()
    gcs_provider = GcsProvider()
    ai_provider = AiProvider(Analysis)
    analysis_repo = AnalysisRepository(engine=db_engine)
    file_record_repo = FileRecordsRepository(engine=db_engine)
    procurement_repo = ProcurementsRepository(engine=db_engine, pubsub_provider=pubsub_provider)
    status_history_repo = StatusHistoryRepository(engine=db_engine)
    budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)
    analysis_service = AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        file_record_repo=file_record_repo,
        status_history_repo=status_history_repo,
        budget_ledger_repo=budget_ledger_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
        pubsub_provider=pubsub_provider,
    )

    with (
        patch("public_detective.repositories.procurements.requests.get", side_effect=mock_requests_get),
        patch.object(ai_provider, "count_tokens_for_analysis", return_value=(1000, 0)),
    ):
        analysis_service.run_pre_analysis(date(2025, 8, 23), date(2025, 8, 23), 10, 0)

    with db_engine.connect() as connection:
        # Check total count
        total_query = text("SELECT COUNT(*) FROM procurements")
        procurement_count = connection.execute(total_query).scalar_one()
        assert procurement_count == len(
            procurement_list_fixture
        ), f"Expected {len(procurement_list_fixture)} procurements, but found {procurement_count} in the database."

        # Check a specific procurement and analysis
        target_procurement = procurement_list_fixture[0]
        pcn = target_procurement["numeroControlePNCP"]
        procurement_query = text("SELECT version_number, raw_data FROM procurements WHERE pncp_control_number = :pcn")
        db_procurement = connection.execute(procurement_query, {"pcn": pcn}).fetchone()
        assert db_procurement is not None, f"No procurement found in the database for {pcn}"
        version, raw_data = db_procurement
        assert version == 1
        assert raw_data["anoCompra"] == target_procurement["anoCompra"]

        analysis_query = text(
            "SELECT version_number, status, input_tokens_used, output_tokens_used FROM procurement_analyses WHERE "
            "procurement_control_number = :pcn"
        )
        db_analysis = connection.execute(analysis_query, {"pcn": pcn}).fetchone()
        assert db_analysis is not None, f"No analysis found in the database for {pcn}"
        version, status, input_tokens_used, output_tokens_used = db_analysis
        assert version == 1
        assert status == "PENDING_ANALYSIS"
        assert input_tokens_used == 1000
        assert output_tokens_used == 0
