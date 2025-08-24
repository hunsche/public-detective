import json
import time
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from google.cloud import pubsub_v1
from models.analysis import Analysis
from source.cli.commands import analysis_command as cli_main
from source.worker.subscription import Subscription
from sqlalchemy import create_engine, text


@pytest.fixture(scope="module")
def docker_services():
    """
    Starts and stops the docker-compose services for the integration test module.
    """
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_DB", "public_detective")
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "postgres")
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")
    
    import subprocess

    subprocess.run("docker compose up -d --build", shell=True, check=True)
    time.sleep(15)
    subprocess.run("poetry run alembic upgrade head", shell=True, check=True)
    yield
    subprocess.run("docker compose down -v --remove-orphans", shell=True, check=True)


@pytest.mark.timeout(30)
@patch("source.repositories.procurement.requests.get")
def test_cli_publishes_message(mock_requests_get, docker_services):
    """
    Tests that the CLI correctly fetches data from a mocked API
    and publishes a valid message to the Pub/Sub emulator.
    """
    # --- Setup ---
    procurement_control_number = "12345678901234-1-000001/2025"
    project_id = "public-detective"
    subscription_name = "procurements-subscription"

    monkeypatch.setenv("GCP_GCS_HOST", "http://localhost:8086")

    file_content = b"This is a test document."
    ai_response = Analysis(
        risk_score=7,
        risk_score_rationale="High risk detected.",
        summary="This is a summary.",
        red_flags=[],
    )

    mock_proc_repo.return_value.process_procurement_documents.return_value = (
        [("test.docx", file_content)],
        [("test.docx", file_content)],
    )
    mock_ai_provider.return_value.get_structured_analysis.return_value = ai_response

    service = AnalysisService()
    procurement_data = {
        "processo": "123",
        "objetoCompra": "Test Object",
        "amparoLegal": {"codigo": 1, "nome": "Test", "descricao": "Test"},
        "srp": False,
        "orgaoEntidade": {
            "cnpj": "00000000000191",
            "razaoSocial": "Test Entity",
            "poderId": "E",
            "esferaId": "F",
        },
        "anoCompra": 2025,
        "sequencialCompra": 1,
        "dataPublicacaoPncp": "2025-01-01T12:00:00",
        "dataAtualizacao": "2025-01-01T12:00:00",
        "numeroCompra": "1",
        "unidadeOrgao": {
            "ufNome": "Test",
            "codigoUnidade": "1",
            "nomeUnidade": "Test",
            "ufSigla": "TE",
            "municipioNome": "Test",
            "codigoIbge": "1",
        },
        "modalidadeId": 8,
        "numeroControlePNCP": "integration-test-123",
        "dataAtualizacaoGlobal": "2025-01-01T12:00:00",
        "modoDisputaId": 5,
        "situacaoCompraId": 1,
        "usuarioNome": "Test User",
    # --- Mock API Response ---
    mock_requests_get.return_value.status_code = 200
    mock_requests_get.return_value.json.return_value = {
        "data": [{"anoCompra": 2025, "sequencialCompra": 1, "numeroControlePncp": procurement_control_number, "orgaoEntidade": {"cnpj": "12345678901234", "razaoSocial": "TEST MOCK", "poderId": "E", "esferaId": "M"}, "modalidadeLicitacao": {"id": 8, "nome": "Dispensa"}, "numeroCompra": "001/2025", "processo": "123/2025", "objetoCompra": "Test Object", "amparoLegal": {"id": 1, "nome": "Art. 24, II", "codigo": "123", "descricao": "Desc"}, "srp": False, "dataPublicacaoPncp": "2025-08-23T10:00:00", "dataAtualizacao": "2025-08-23T10:00:00", "unidadeOrgao": {"nomeUnidade": "Test Unit", "codigoUnidade": "123", "ufNome": "Test", "municipioNome": "Test", "codigoIbge": "123", "ufSigla": "T"}, "modalidadeId": 8, "numeroControlePNCP": procurement_control_number, "dataAtualizacaoGlobal": "2025-08-23T10:00:00", "modoDisputaId": 1, "situacaoCompraId": 1, "usuarioNome": "Test User"}],
        "totalPaginas": 1, "totalRegistros": 1, "numeroPagina": 1
    }

    # --- Execute CLI ---
    runner = CliRunner()
    result = runner.invoke(cli_main, ["--start-date", "2025-08-23", "--end-date", "2025-08-23"])
    assert result.exit_code == 0
    assert "Analysis completed successfully!" in result.output

    # --- Verification ---
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(project_id, subscription_name)
    response = subscriber.pull(subscription=subscription_path, max_messages=1, timeout=10)
    assert len(response.received_messages) == 1, "CLI did not publish a message."
    message_data = json.loads(response.received_messages[0].message.data)
    assert message_data["numeroControlePncp"] == procurement_control_number

    # --- Cleanup ---
    ack_id = response.received_messages[0].ack_id
    subscriber.acknowledge(subscription=subscription_path, ack_ids=[ack_id])


@pytest.mark.timeout(30)
@patch("source.worker.subscription.Subscription._debug_pause", lambda self, prompt: None)
@patch("source.providers.ai.AiProvider.get_structured_analysis")
@patch("source.repositories.procurement.ProcurementRepository._download_file_content")
@patch("source.repositories.procurement.requests.get")
def test_worker_processes_message(mock_requests_get, mock_download, mock_get_analysis, docker_services):
    """
    Tests that the Worker correctly consumes a message, processes it with mocked
    dependencies, and saves the result to the database.
    """
    # --- Setup ---
    procurement_control_number = "98765432109876-1-000002/2025"
    project_id = "public-detective"
    topic_name = "procurements"

    # --- Mock Dependencies ---
    mock_document_list = MagicMock()
    mock_document_list.status_code = 200
    mock_document_list.json.return_value = [{"url": "http://fake.url/document.pdf", "document_sequence": 1, "document_type_name": "Edital", "is_active": True, "title": "document.pdf", "document_type_id": 1}]
    mock_requests_get.return_value = mock_document_list
    mock_download.return_value = b"fake pdf content"
    mock_get_analysis.return_value = Analysis(risk_score=5, risk_score_rationale="Mocked medium risk.", summary="This is another mocked summary.", red_flags=[])

    # --- Publish a Message Manually ---
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_name)
    message_data = {"anoCompra": 2025, "sequencialCompra": 2, "numeroControlePncp": procurement_control_number, "orgaoEntidade": {"cnpj": "98765432109876", "razaoSocial": "TEST MOCK 2", "poderId": "E", "esferaId": "M"}, "modalidadeLicitacao": {"id": 8, "nome": "Dispensa"}, "numeroCompra": "002/2025", "processo": "456/2025", "objetoCompra": "Test Object 2", "amparoLegal": {"id": 1, "nome": "Art. 24, II", "codigo": "456", "descricao": "Desc 2"}, "srp": False, "dataPublicacaoPncp": "2025-08-23T11:00:00", "dataAtualizacao": "2025-08-23T11:00:00", "unidadeOrgao": {"nomeUnidade": "Test Unit 2", "codigoUnidade": "456", "ufNome": "Test2", "municipioNome": "Test2", "codigoIbge": "456", "ufSigla": "T2"}, "modalidadeId": 8, "numeroControlePNCP": procurement_control_number, "dataAtualizacaoGlobal": "2025-08-23T11:00:00", "modoDisputaId": 1, "situacaoCompraId": 1, "usuarioNome": "Test User 2"}
    publisher.publish(topic_path, json.dumps(message_data).encode("utf-8"))

    # --- Execute Worker ---
    subscription = Subscription()
    subscription.run(max_messages=1)

    # --- Verification ---
    db_url = "postgresql://postgres:postgres@localhost:5432/public_detective"
    engine = create_engine(db_url)
    with engine.connect() as connection:
        result = connection.execute(text("SELECT risk_score, summary FROM procurement_analysis WHERE procurement_control_number = :pcn"), {"pcn": procurement_control_number}).fetchone()

    assert result is not None
    risk_score, summary = result
    assert risk_score == 5
    assert summary == "This is another mocked summary."
