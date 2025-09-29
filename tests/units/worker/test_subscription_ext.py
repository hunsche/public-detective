import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import GoogleAPICallError
from public_detective.exceptions.analysis import AnalysisError
from public_detective.worker.subscription import Subscription
from pydantic import ValidationError


@pytest.fixture
def mock_analysis_service():
    """Provides a mock AnalysisService."""
    service = MagicMock()
    service.analysis_repo.get_analysis_by_id.return_value = MagicMock()
    return service


@pytest.fixture
def subscription(mock_analysis_service):
    """Provides a Subscription instance with a mocked service."""
    return Subscription(analysis_service=mock_analysis_service)


def test_extend_ack_deadline_failure(subscription):
    """Tests that a failure to extend the ack deadline is logged and handled."""
    mock_message = MagicMock()
    mock_message.modify_ack_deadline.side_effect = GoogleAPICallError("API Error")
    with patch.object(subscription, "logger") as mock_logger:
        subscription._extend_ack_deadline(mock_message, 60)
        mock_logger.debug.assert_called_with("Unable to extend ack deadline; continuing.")


def test_debug_pause_eof_error(subscription):
    """Tests that an EOFError in _debug_pause is handled gracefully."""
    with patch("builtins.input", side_effect=EOFError), patch.object(subscription, "logger") as mock_logger:
        subscription._debug_pause()
        mock_logger.debug.assert_called_with("No TTY available; skipping pause.")


def test_process_message_analysis_not_found(subscription):
    """Tests processing a message where the analysis ID is not found."""
    subscription.analysis_service.analysis_repo.get_analysis_by_id.return_value = None
    mock_message = MagicMock()
    mock_message.data = json.dumps({"analysis_id": "some-id"}).encode("utf-8")

    subscription._process_message(mock_message)

    mock_message.nack.assert_called_once()


def test_process_message_json_decode_error(subscription):
    """Tests processing a message with invalid JSON data."""
    mock_message = MagicMock()
    mock_message.data = b"this is not json"

    subscription._process_message(mock_message)

    mock_message.nack.assert_called_once()


def test_process_message_validation_error(subscription):
    """Tests processing a message with data that fails Pydantic validation."""
    mock_message = MagicMock()
    # Missing 'analysis_id' will cause a validation error at some point,
    # but we will mock json.loads to raise it directly for this unit test.
    mock_message.data = json.dumps({"some_other_key": "value"}).encode("utf-8")
    with patch("json.loads", side_effect=ValidationError.from_exception_data("error", [])):
        subscription._process_message(mock_message)
        mock_message.nack.assert_called_once()


def test_process_message_analysis_error(subscription):
    """Tests that an AnalysisError from the service results in a NACK."""
    subscription.analysis_service.process_analysis_from_message.side_effect = AnalysisError("Service failed")
    mock_message = MagicMock()
    mock_message.data = json.dumps({"analysis_id": "some-id"}).encode("utf-8")

    subscription._process_message(mock_message)

    mock_message.nack.assert_called_once()


def test_message_callback_when_stopped(subscription):
    """Tests that messages are NACKed if the stop event is set."""
    subscription._stop_event.set()
    mock_message = MagicMock()

    subscription._message_callback(mock_message, max_messages=10)

    mock_message.nack.assert_called_once()


def test_run_with_no_subscription_name(subscription, caplog):
    """Tests that the worker does not start if no subscription name is configured."""
    subscription.config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS = ""
    subscription.run()
    assert "Subscription name not configured. Worker cannot start." in caplog.text
