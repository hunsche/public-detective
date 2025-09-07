import json
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import GoogleAPICallError
from worker.subscription import Subscription
from exceptions.analysis import AnalysisError


@pytest.fixture
def mock_message() -> MagicMock:
    message_data = {"analysis_id": 123}
    message = MagicMock()
    message.data = json.dumps(message_data).encode("utf-8")
    message.message_id = "test-message-id"
    return message


@pytest.fixture
def mock_analysis_service() -> MagicMock:
    """Fixture for a mocked AnalysisService."""
    service = MagicMock()
    service.procurement_repo = MagicMock()
    return service


@pytest.fixture
def subscription(mock_analysis_service: MagicMock) -> Subscription:
    """Fixture to create a Subscription instance with mocked services."""
    sub = Subscription(analysis_service=mock_analysis_service)
    sub.pubsub_provider = MagicMock()
    return sub


@pytest.mark.parametrize(
    "side_effect, acks, nacks",
    [
        (None, 1, 0),
        (AnalysisError("test error"), 0, 1),
        (Exception("test error"), 0, 1),
    ],
)
def test_process_message(
    subscription: Subscription,
    mock_message: MagicMock,
    side_effect: Exception | None,
    acks: int,
    nacks: int,
) -> None:
    """Tests message processing under various conditions."""
    subscription.analysis_service.process_analysis_from_message.side_effect = side_effect
    subscription.config.IS_DEBUG_MODE = False

    subscription._process_message(mock_message, max_output_tokens=None)

    assert mock_message.ack.call_count == acks
    assert mock_message.nack.call_count == nacks


def test_process_message_validation_error(subscription: Subscription) -> None:
    """Tests that a message with invalid data is NACKed."""
    invalid_message = MagicMock()
    invalid_message.data = b"invalid json"
    invalid_message.message_id = "invalid-message"

    subscription._process_message(invalid_message, max_output_tokens=None)

    invalid_message.nack.assert_called_once()
    invalid_message.ack.assert_not_called()




def test_message_callback_stops_at_max_messages(subscription: Subscription, mock_message: MagicMock) -> None:
    """Tests that the worker stops after reaching the message limit."""
    subscription.streaming_pull_future = MagicMock()
    subscription._process_message = MagicMock()

    subscription._message_callback(mock_message, max_messages=1, max_output_tokens=None)

    assert subscription.processed_messages_count == 1
    assert subscription._stop_event.is_set()
    subscription.streaming_pull_future.cancel.assert_called_once()


def test_run_worker(subscription: Subscription) -> None:
    """Tests that the worker subscribes and runs correctly."""
    future = MagicMock()
    subscription.pubsub_provider.subscribe.return_value = future
    subscription.run()
    subscription.pubsub_provider.subscribe.assert_called_once()
    future.result.assert_called_once()


def test_run_worker_handles_shutdown_exception(subscription: Subscription) -> None:
    """Tests graceful shutdown on common exceptions."""
    future = MagicMock()
    future.result.side_effect = [TimeoutError("Test timeout"), None]
    future.cancelled.return_value = False
    subscription.pubsub_provider.subscribe.return_value = future
    subscription.run()
    future.cancel.assert_called_once()
    assert future.result.call_count == 2


def test_run_worker_no_subscription_name(subscription: Subscription) -> None:
    """Tests that the worker exits if the subscription name is not configured."""
    subscription.config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS = None
    subscription.pubsub_provider = MagicMock()
    subscription.run()
    subscription.pubsub_provider.subscribe.assert_not_called()


def test_extend_ack_deadline(subscription: Subscription, mock_message: MagicMock) -> None:
    """Tests the extend_ack_deadline method."""
    subscription._extend_ack_deadline(mock_message, 120)
    mock_message.modify_ack_deadline.assert_called_once_with(120)


@patch("worker.subscription.AnalysisService")
@patch("worker.subscription.FileRecordsRepository")
@patch("worker.subscription.AnalysisRepository")
@patch("worker.subscription.ProcurementsRepository")
@patch("worker.subscription.AiProvider")
@patch("worker.subscription.GcsProvider")
@patch("worker.subscription.DatabaseManager")
def test_subscription_init_composition_root(
    mock_db_manager: MagicMock,
    mock_gcs_provider: MagicMock,
    mock_ai_provider: MagicMock,
    mock_procurement_repo: MagicMock,
    mock_analysis_repo: MagicMock,
    mock_file_record_repo: MagicMock,
    mock_analysis_service: MagicMock,
) -> None:
    """Tests that the Subscription class correctly wires up dependencies."""
    sub = Subscription(analysis_service=None)

    mock_db_manager.get_engine.assert_called_once()
    mock_gcs_provider.assert_called_once()
    mock_ai_provider.assert_called_once()
    mock_procurement_repo.assert_called_once()
    mock_analysis_repo.assert_called_once()
    mock_file_record_repo.assert_called_once()
    mock_analysis_service.assert_called_once()

    _, kwargs = mock_analysis_service.call_args
    assert kwargs["procurement_repo"] is not None
    assert kwargs["analysis_repo"] is not None
    assert kwargs["file_record_repo"] is not None
    assert kwargs["ai_provider"] is not None
    assert kwargs["gcs_provider"] is not None

    assert sub.analysis_service is not None


@patch("worker.subscription.AnalysisService")
@patch("worker.subscription.DatabaseManager")
def test_subscription_init_no_service(mock_db_manager, mock_analysis_service):
    """Test that the Subscription class can be initialized without a service."""
    Subscription()
    mock_db_manager.get_engine.assert_called_once()
    mock_analysis_service.assert_called_once()


def test_extend_ack_deadline_exception(subscription: Subscription, mock_message: MagicMock) -> None:
    """Tests that an exception in modify_ack_deadline is handled."""
    mock_message.modify_ack_deadline.side_effect = Exception("test error")
    subscription._extend_ack_deadline(mock_message, 120)


def test_debug_pause_eof_error(subscription: Subscription) -> None:
    """Tests that an EOFError during input is handled."""
    with patch("builtins.input", side_effect=EOFError):
        subscription._debug_pause()


def test_run_worker_critical_error(subscription: Subscription) -> None:
    """Tests that a critical, non-shutdown error is logged."""
    future = MagicMock()
    future.result.side_effect = Exception("Critical error")
    subscription.pubsub_provider.subscribe.return_value = future
    subscription.logger = MagicMock()

    subscription.run()

    assert any("critical" in call[0][0].lower() for call in subscription.logger.critical.call_args_list)


def test_message_callback_stop_event_set(subscription: Subscription, mock_message: MagicMock) -> None:
    """Tests that the callback returns early if the stop event is set."""
    subscription._stop_event.set()
    subscription._process_message = MagicMock()

    subscription._message_callback(mock_message, max_messages=1, max_output_tokens=None)

    subscription._process_message.assert_not_called()




def test_message_callback_no_max_messages(subscription: Subscription, mock_message: MagicMock) -> None:
    """Tests that the worker does not stop if max_messages is not set."""
    subscription.streaming_pull_future = MagicMock()
    subscription._process_message = MagicMock()

    subscription._message_callback(mock_message, max_messages=None, max_output_tokens=None)

    assert subscription.processed_messages_count == 1
    assert not subscription._stop_event.is_set()
    subscription.streaming_pull_future.cancel.assert_not_called()


@pytest.mark.parametrize("exception", [GoogleAPICallError("API Error")])
def test_run_worker_handles_shutdown_exceptions(subscription: Subscription, exception: Exception) -> None:
    """Tests graceful shutdown on common exceptions."""
    future = MagicMock()
    future.result.side_effect = exception
    future.cancelled.return_value = False
    subscription.pubsub_provider.subscribe.return_value = future

    subscription.run()

    future.cancel.assert_called_once()


@pytest.mark.skip(reason="KeyboardInterrupt cannot be caught by pytest")
def test_run_worker_keyboard_interrupt(subscription: Subscription) -> None:
    """Tests graceful shutdown on KeyboardInterrupt."""
    future = MagicMock()
    future.result.side_effect = KeyboardInterrupt()
    future.cancelled.return_value = False
    subscription.pubsub_provider.subscribe.return_value = future

    subscription.run()

    future.cancel.assert_called_once()


def test_run_worker_finally_block_exception(subscription: Subscription) -> None:
    """
    Tests that an exception in the finally block's result() call is handled.
    """
    future = MagicMock()
    future.result.side_effect = [TimeoutError("Test timeout"), Exception("Final result error")]
    future.cancelled.return_value = False
    subscription.pubsub_provider.subscribe.return_value = future

    # This should not raise an exception
    subscription.run()

    future.cancel.assert_called_once()
    assert future.result.call_count == 2
