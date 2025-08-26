from unittest.mock import MagicMock, patch

import pytest
from models.procurement import Procurement
from worker.subscription import Subscription


@pytest.fixture
def mock_message():
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
        "numeroControlePNCP": "12345",
        "dataAtualizacaoGlobal": "2025-01-01T12:00:00",
        "modoDisputaId": 5,
        "situacaoCompraId": 1,
        "usuarioNome": "Test User",
    }
    procurement = Procurement.model_validate(procurement_data)
    message = MagicMock()
    message.data = procurement.model_dump_json(by_alias=True).encode("utf-8")
    message.message_id = "test-message-id"
    return message


@patch("worker.subscription.AnalysisService")
@patch("worker.subscription.ProcurementRepository")
def test_process_message_success(mock_proc_repo, mock_analysis_service, mock_message):
    """Tests the successful processing of a valid message."""
    sub = Subscription()
    sub.config.IS_DEBUG_MODE = False
    sub._process_message(mock_message)

    mock_proc_repo.return_value.save_procurement.assert_called_once()
    mock_analysis_service.return_value.analyze_procurement.assert_called_once()
    mock_message.ack.assert_called_once()
    mock_message.nack.assert_not_called()


def test_process_message_validation_error():
    """Tests that a message with invalid data is NACKed."""
    sub = Subscription()
    invalid_message = MagicMock()
    invalid_message.data = b"invalid json"
    invalid_message.message_id = "invalid-message"

    sub._process_message(invalid_message)

    invalid_message.nack.assert_called_once()
    invalid_message.ack.assert_not_called()


@patch("worker.subscription.AnalysisService")
def test_process_message_unexpected_error(mock_analysis_service, mock_message):
    """Tests that an unexpected error during processing results in a NACK."""
    mock_analysis_service.return_value.analyze_procurement.side_effect = Exception("Boom!")
    sub = Subscription()
    sub.config.IS_DEBUG_MODE = False

    sub._process_message(mock_message)

    mock_message.nack.assert_called_once()
    mock_message.ack.assert_not_called()


def test_message_callback_stops_at_max_messages(mock_message):
    """Tests that the worker stops after reaching the message limit."""
    sub = Subscription()
    sub.streaming_pull_future = MagicMock()
    sub._process_message = MagicMock()

    sub._message_callback(mock_message, max_messages=1)

    assert sub.processed_messages_count == 1
    assert sub._stop_event.is_set()
    sub.streaming_pull_future.cancel.assert_called_once()


@patch("worker.subscription.PubSubProvider")
def test_run_worker(mock_pubsub_provider):
    """Tests that the worker subscribes and runs correctly."""
    future = MagicMock()
    mock_pubsub_provider.return_value.subscribe.return_value = future
    sub = Subscription()

    sub.run()

    mock_pubsub_provider.return_value.subscribe.assert_called_once()
    future.result.assert_called_once()


@patch("worker.subscription.PubSubProvider")
def test_run_worker_handles_shutdown_exception(mock_pubsub_provider):
    """Tests graceful shutdown on common exceptions."""
    future = MagicMock()
    future.result.side_effect = [TimeoutError("Test timeout"), None]
    future.cancelled.return_value = False
    mock_pubsub_provider.return_value.subscribe.return_value = future
    sub = Subscription()

    sub.run()

    future.cancel.assert_called_once()
    assert future.result.call_count == 2


def test_run_worker_no_subscription_name():
    """Tests that the worker exits if the subscription name is not configured."""
    sub = Subscription()
    sub.config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS = None
    sub.pubsub_provider = MagicMock()

    sub.run()

    sub.pubsub_provider.subscribe.assert_not_called()


@patch("worker.subscription.Subscription._extend_ack_deadline")
def test_debug_context(mock_extend_ack, mock_message):
    """Tests that the debug context extends the ack deadline."""
    sub = Subscription()
    sub.config.IS_DEBUG_MODE = True
    with sub._debug_context(mock_message):
        pass
    mock_extend_ack.assert_called_once_with(mock_message, 600)


def test_extend_ack_deadline(mock_message):
    """Tests the extend_ack_deadline method."""
    sub = Subscription()
    sub._extend_ack_deadline(mock_message, 120)
    mock_message.modify_ack_deadline.assert_called_once_with(120)


@patch("builtins.input")
def test_debug_pause(mock_input):
    """Tests the debug_pause method."""
    sub = Subscription()
    sub._debug_pause()
    mock_input.assert_called_once()
