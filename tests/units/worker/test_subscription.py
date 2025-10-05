import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import GoogleAPICallError
from public_detective.exceptions.analysis import AnalysisError
from public_detective.worker.subscription import Subscription
from pydantic import ValidationError


@pytest.fixture
def mock_message() -> MagicMock:
    message_data = {"analysis_id": "123"}
    message = MagicMock()
    message.data = json.dumps(message_data).encode("utf-8")
    message.message_id = "test-message-id"
    return message


@pytest.fixture
def mock_analysis_service() -> MagicMock:
    """Fixture for a mocked AnalysisService."""
    service = MagicMock()
    service.analysis_repo.get_analysis_by_id.return_value = MagicMock()
    return service


@pytest.fixture
def subscription(mock_analysis_service: MagicMock) -> Subscription:
    """Fixture to create a Subscription instance with mocked services."""
    sub = Subscription(analysis_service=mock_analysis_service)
    sub.pubsub_provider = MagicMock()
    return sub


def test_process_message_success(subscription: Subscription, mock_message: MagicMock) -> None:
    subscription.config.FORCE_SYNC = False
    subscription._process_message(mock_message, max_output_tokens=None)

    subscription.analysis_service.process_analysis_from_message.assert_called_once_with("123", max_output_tokens=None)
    mock_message.ack.assert_called_once()
    mock_message.nack.assert_not_called()


def test_process_message_validation_error(subscription: Subscription) -> None:
    """Tests that a message with invalid data is NACKed."""
    invalid_message = MagicMock()
    invalid_message.data = b'{"wrong_key": "value"}'
    invalid_message.message_id = "invalid-message"

    subscription._process_message(invalid_message, max_output_tokens=None)

    invalid_message.nack.assert_called_once()
    invalid_message.ack.assert_not_called()


def test_process_message_unexpected_error(subscription: Subscription, mock_message: MagicMock) -> None:
    """Tests that an unexpected error during processing results in a NACK."""
    subscription.analysis_service.process_analysis_from_message.side_effect = Exception("Boom!")
    subscription.config.FORCE_SYNC = False

    subscription._process_message(mock_message, max_output_tokens=None)

    mock_message.nack.assert_called_once()
    mock_message.ack.assert_not_called()


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


def test_run_worker_handles_generic_exception(subscription: Subscription, caplog: Any) -> None:
    """Tests that a generic, non-cancellation exception is logged as critical."""
    future = MagicMock()
    future.result.side_effect = Exception("Something went wrong")
    subscription.pubsub_provider.subscribe.return_value = future

    subscription.run()

    assert "A critical error stopped the worker: Something went wrong" in caplog.text


def test_run_worker_no_subscription_name(subscription: Subscription, caplog: Any) -> None:
    """Tests that the worker exits if the subscription name is not configured."""
    subscription.config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS = ""
    subscription.run()
    assert "Subscription name not configured. Worker cannot start." in caplog.text


def test_debug_context(subscription: Subscription, mock_message: MagicMock) -> None:
    """Tests that the debug context extends the ack deadline."""
    subscription.config.FORCE_SYNC = True
    subscription._extend_ack_deadline = MagicMock()
    with subscription._debug_context(mock_message):
        pass
    subscription._extend_ack_deadline.assert_called_once_with(mock_message, 600)


def test_extend_ack_deadline(subscription: Subscription, mock_message: MagicMock) -> None:
    """Tests the extend_ack_deadline method."""
    subscription._extend_ack_deadline(mock_message, 120)
    mock_message.modify_ack_deadline.assert_called_once_with(120)


def test_debug_pause(subscription: Subscription) -> None:
    """Tests the debug_pause method."""
    with patch("builtins.input"):
        subscription._debug_pause()


@patch("public_detective.worker.subscription.AnalysisService")
@patch("public_detective.worker.subscription.FileRecordsRepository")
@patch("public_detective.worker.subscription.AnalysisRepository")
@patch("public_detective.worker.subscription.ProcurementsRepository")
@patch("public_detective.worker.subscription.AiProvider")
@patch("public_detective.worker.subscription.GcsProvider")
@patch("public_detective.worker.subscription.DatabaseManager")
def test_subscription_init_composition_root(
    _mock_db_manager: MagicMock,
    _mock_gcs_provider: MagicMock,
    _mock_ai_provider: MagicMock,
    _mock_procurement_repo: MagicMock,
    _mock_analysis_repo: MagicMock,
    _mock_file_record_repo: MagicMock,
    mock_analysis_service: MagicMock,
) -> None:
    """Tests that the Subscription class correctly wires up dependencies."""
    Subscription(analysis_service=None)
    mock_analysis_service.assert_called_once()


def test_extend_ack_deadline_failure(subscription: Subscription) -> None:
    """Tests that a failure to extend the ack deadline is logged and handled."""
    mock_message = MagicMock()
    mock_message.modify_ack_deadline.side_effect = GoogleAPICallError("API Error")
    with patch.object(subscription, "logger") as mock_logger:
        subscription._extend_ack_deadline(mock_message, 60)
        mock_logger.debug.assert_called_with("Unable to extend ack deadline; continuing.")


def test_debug_pause_eof_error(subscription: Subscription) -> None:
    """Tests that an EOFError in _debug_pause is handled gracefully."""
    with patch("builtins.input", side_effect=EOFError), patch.object(subscription, "logger") as mock_logger:
        subscription._debug_pause()
        mock_logger.debug.assert_called_with("No TTY available; skipping pause.")


def test_process_message_analysis_not_found(subscription: Subscription) -> None:
    """Tests processing a message where the analysis ID is not found."""
    subscription.analysis_service.analysis_repo.get_analysis_by_id.return_value = None
    mock_message = MagicMock()
    mock_message.data = json.dumps({"analysis_id": "some-id"}).encode("utf-8")
    subscription._process_message(mock_message)
    mock_message.nack.assert_called_once()


def test_process_message_json_decode_error(subscription: Subscription) -> None:
    """Tests processing a message with invalid JSON data."""
    mock_message = MagicMock()
    mock_message.data = b"this is not json"
    subscription._process_message(mock_message)
    mock_message.nack.assert_called_once()


def test_process_message_validation_error_on_load(subscription: Subscription) -> None:
    """Tests processing a message with data that fails Pydantic validation."""
    mock_message = MagicMock()
    mock_message.data = json.dumps({"some_other_key": "value"}).encode("utf-8")
    with patch("json.loads", side_effect=ValidationError.from_exception_data("error", [])):
        subscription._process_message(mock_message)
        mock_message.nack.assert_called_once()


def test_process_message_analysis_error(subscription: Subscription) -> None:
    """Tests that an AnalysisError from the service results in a NACK."""
    subscription.analysis_service.process_analysis_from_message.side_effect = AnalysisError("Service failed")
    mock_message = MagicMock()
    mock_message.data = json.dumps({"analysis_id": "some-id"}).encode("utf-8")
    subscription._process_message(mock_message)
    mock_message.nack.assert_called_once()


def test_message_callback_when_stopped(subscription: Subscription) -> None:
    """Tests that messages are NACKed if the stop event is set."""
    subscription._stop_event.set()
    mock_message = MagicMock()
    subscription._message_callback(mock_message, max_messages=10)
    mock_message.nack.assert_called_once()


def test_message_callback_no_max_messages(subscription: Subscription, mock_message: MagicMock) -> None:
    """Tests that the worker does not stop if max_messages is None."""
    subscription.streaming_pull_future = MagicMock()
    subscription._process_message = MagicMock()

    subscription._message_callback(mock_message, max_messages=None, max_output_tokens=None)

    assert not subscription._stop_event.is_set()
    subscription.streaming_pull_future.cancel.assert_not_called()
