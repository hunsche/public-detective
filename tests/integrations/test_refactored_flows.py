import io
import json
import os
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest
import requests
from click.testing import CliRunner
from models.analysis import Analysis
from services.analysis import AnalysisService
from sqlalchemy import text

from source.cli.commands import pre_analyze_command as cli_main
from source.providers.ai import AiProvider
from source.providers.gcs import GcsProvider
from source.providers.pubsub import PubSubProvider
from source.repositories.analysis import AnalysisRepository
from source.repositories.file_record import FileRecordRepository
from source.repositories.procurement import ProcurementRepository
from source.worker.subscription import Subscription
from tests.integrations.test_full_flow import load_binary_fixture, load_fixture


@pytest.mark.skip(reason="Ignoring integration tests for now as per user request.")
@pytest.mark.timeout(180)
def test_pre_analyze_flow(integration_test_setup, db_session):  # noqa: F841
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
    with (
        patch("source.repositories.procurement.requests.get", side_effect=mock_requests_get),
        patch("source.cli.commands.AiProvider") as mock_ai_provider,
    ):
        mock_ai_provider.return_value.count_tokens_for_analysis.return_value = 10000
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


@pytest.mark.skip(reason="Ignoring integration tests for now as per user request.")
@pytest.mark.timeout(180)
def test_analysis_worker_flow(integration_test_setup, db_session):  # noqa: F841
    fixture_base_path = "tests/fixtures/3304557/2025-08-23"
    procurement_list_fixture = load_fixture(f"{fixture_base_path}/pncp_procurement_list.json")
    document_list_fixture = load_fixture(f"{fixture_base_path}/pncp_document_list.json")
    attachments_fixture = load_binary_fixture(f"{fixture_base_path}/Anexos.zip")
    gemini_response_fixture = Analysis.model_validate(load_fixture(f"{fixture_base_path}/gemini_response.json"))

    def mock_requests_get(url, **kwargs):
        mock_response = requests.Response()
        mock_response.status_code = 200
        if url.endswith("/arquivos"):
            mock_response.json = lambda: document_list_fixture
        elif "/arquivos/" in url:
            mock_response._content = attachments_fixture
            mock_response.headers["Content-Disposition"] = 'attachment; filename="Anexos.zip"'
        else:
            mock_response.status_code = 404
        return mock_response

    db_engine = db_session
    pubsub_provider = PubSubProvider()

    # Manually create a procurement and a pending analysis
    procurement_data = procurement_list_fixture[0]
    pcn = procurement_data["numeroControlePNCP"]
    with db_engine.connect() as connection:
        connection.execute(
            text(
                "INSERT INTO procurement (pncp_control_number, object_description, raw_data, "
                "is_srp, procurement_year, procurement_sequence, pncp_publication_date, "
                "last_update_date, modality_id, procurement_status_id) "
                "VALUES (:pcn, 'test description', :raw_data, false, 2024, 1, now(), now(), 1, 1)"
            ),
            {"pcn": pcn, "raw_data": json.dumps(procurement_data)},
        )
        connection.execute(
            text(
                "INSERT INTO procurement_analysis (procurement_control_number, status) "
                "VALUES (:pcn, 'PENDING_ANALYSIS')"
            ),
            {"pcn": pcn},
        )
        connection.commit()

    # Publish a message to the topic
    message_data = {"procurement_control_number": pcn}
    pubsub_provider.publish(
        topic_id=os.environ["GCP_PUBSUB_TOPIC_PROCUREMENTS"],
        data=json.dumps(message_data).encode("utf-8"),
    )

    # Setup service and worker
    ai_provider = AiProvider(Analysis)
    analysis_repo = AnalysisRepository(engine=db_engine)
    file_record_repo = FileRecordRepository(engine=db_engine)
    procurement_repo = ProcurementRepository(engine=db_engine, pubsub_provider=pubsub_provider)
    gcs_provider = GcsProvider()
    analysis_service = AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        file_record_repo=file_record_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
    )
    subscription = Subscription(analysis_service=analysis_service)

    with (
        patch("source.repositories.procurement.requests.get", side_effect=mock_requests_get),
        patch("source.providers.ai.AiProvider.get_structured_analysis", return_value=gemini_response_fixture),
        patch("google.generativeai.configure"),
        patch("google.generativeai.GenerativeModel"),
    ):
        log_capture_stream = io.StringIO()
        with redirect_stdout(log_capture_stream):
            subscription.run(max_messages=1)

    with db_engine.connect() as connection:
        specific_query = text(
            "SELECT status, risk_score FROM procurement_analysis WHERE " "procurement_control_number = :pcn"
        )
        db_result = connection.execute(specific_query, {"pcn": pcn}).fetchone()

        assert db_result is not None, f"No analysis found in the database for {pcn}"
        status, risk_score = db_result
        assert status == "ANALYSIS_SUCCESSFUL"
        assert risk_score == gemini_response_fixture.risk_score
