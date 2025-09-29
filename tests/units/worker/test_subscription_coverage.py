"""
Unit tests for the Subscription worker to increase test coverage.
"""
import threading
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import GoogleAPICallError
from public_detective.worker.subscription import Subscription


def test_process_message_analysis_not_found(subscription: Subscription, mock_message: MagicMock):
    """
    Tests that a message is NACKed if the analysis_id is not found.
    """
    subscription.analysis_service.analysis_repo.get_analysis_by_id.return_value = None

    subscription._process_message(mock_message)

    mock_message.nack.assert_called_once()
    subscription.logger.error.assert_called_once()


def test_process_message_signals_completion_event(subscription: Subscription, mock_message: MagicMock):
    """
    Tests that the processing_complete_event is set in the finally block.
    """
    completion_event = threading.Event()
    subscription._processing_complete_event = completion_event

    subscription._process_message(mock_message)

    assert completion_event.is_set()


def test_run_worker_handles_keyboard_interrupt(subscription: Subscription):
    """Tests graceful shutdown on KeyboardInterrupt."""
    future = MagicMock()
    future.result.side_effect = KeyboardInterrupt
    future.cancelled.return_value = False
    subscription.pubsub_provider.subscribe.return_value = future

    subscription.run()

    subscription.logger.warning.assert_called_with("Shutdown requested: KeyboardInterrupt")
    future.cancel.assert_called_once()


def test_extend_ack_deadline_exception_logs_warning(subscription: Subscription, mock_message: MagicMock):
    """Tests that a warning is logged when extend_ack_deadline fails."""
    mock_message.modify_ack_deadline.side_effect = GoogleAPICallError("API Error")

    subscription._extend_ack_deadline(mock_message, 120)

    subscription.logger.debug.assert_called_with("Unable to extend ack deadline; continuing.")