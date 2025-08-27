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


@pytest.fixture
def mock_analysis_service():
    """Fixture for a mocked AnalysisService."""
    service = MagicMock()
    # The subscription needs a procurement_repo from the service
    service.procurement_repo = MagicMock()
    return service


@pytest.fixture
def subscription(mock_analysis_service):
    """Fixture to create a Subscription instance with mocked services."""
    # We don't need to mock the config provider anymore because the tests
    # that need it will inject a mocked analysis_service, preventing the
    # real AiProvider from being created.
    sub = Subscription(analysis_service=mock_analysis_service)
    # Manually replace the real provider with a mock for these tests
    sub.pubsub_provider = MagicMock()
    return sub


def test_process_message_success(subscription, mock_message):
    """Tests the successful processing of a valid message."""
    subscription.config.IS_DEBUG_MODE = False
    subscription._process_message(mock_message)

    subscription.procurement_repo.save_procurement.assert_called_once()
    subscription.analysis_service.analyze_procurement.assert_called_once()
    mock_message.ack.assert_called_once()
    mock_message.nack.assert_not_called()


def test_process_message_validation_error(subscription):
    """Tests that a message with invalid data is NACKed."""
    invalid_message = MagicMock()
    invalid_message.data = b"invalid json"
    invalid_message.message_id = "invalid-message"

    subscription._process_message(invalid_message)

    invalid_message.nack.assert_called_once()
    invalid_message.ack.assert_not_called()


def test_process_message_unexpected_error(subscription, mock_message):
    """Tests that an unexpected error during processing results in a NACK."""
    subscription.analysis_service.analyze_procurement.side_effect = Exception("Boom!")
    subscription.config.IS_DEBUG_MODE = False

    subscription._process_message(mock_message)

    mock_message.nack.assert_called_once()
    mock_message.ack.assert_not_called()


def test_message_callback_stops_at_max_messages(subscription, mock_message):
    """Tests that the worker stops after reaching the message limit."""
    subscription.streaming_pull_future = MagicMock()
    subscription._process_message = MagicMock()

    subscription._message_callback(mock_message, max_messages=1)

    assert subscription.processed_messages_count == 1
    assert subscription._stop_event.is_set()
    subscription.streaming_pull_future.cancel.assert_called_once()


def test_run_worker(subscription):
    """Tests that the worker subscribes and runs correctly."""
    future = MagicMock()
    subscription.pubsub_provider.subscribe.return_value = future
    subscription.run()
    subscription.pubsub_provider.subscribe.assert_called_once()
    future.result.assert_called_once()


def test_run_worker_handles_shutdown_exception(subscription):
    """Tests graceful shutdown on common exceptions."""
    future = MagicMock()
    future.result.side_effect = [TimeoutError("Test timeout"), None]
    future.cancelled.return_value = False
    subscription.pubsub_provider.subscribe.return_value = future
    subscription.run()
    future.cancel.assert_called_once()
    assert future.result.call_count == 2


def test_run_worker_no_subscription_name(subscription):
    """Tests that the worker exits if the subscription name is not configured."""
    subscription.config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS = None
    # Reset the mock from the fixture to check for no calls
    subscription.pubsub_provider = MagicMock()
    subscription.run()
    subscription.pubsub_provider.subscribe.assert_not_called()


def test_debug_context(subscription, mock_message):
    """Tests that the debug context extends the ack deadline."""
    subscription.config.IS_DEBUG_MODE = True
    subscription._extend_ack_deadline = MagicMock()
    with subscription._debug_context(mock_message):
        pass
    subscription._extend_ack_deadline.assert_called_once_with(mock_message, 600)


def test_extend_ack_deadline(subscription, mock_message):
    """Tests the extend_ack_deadline method."""
    subscription._extend_ack_deadline(mock_message, 120)
    mock_message.modify_ack_deadline.assert_called_once_with(120)


def test_debug_pause(subscription):
    """Tests the debug_pause method."""
    with patch("builtins.input"):
        subscription._debug_pause()
