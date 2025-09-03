import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest
from providers.logging import ContextualFilter, LoggingProvider, _log_context


@pytest.fixture()
def clean_logger():
    """Ensure the logger is clean and the provider is reset for each test."""
    # Reset the singleton state
    LoggingProvider._instance = None
    LoggingProvider._logger = None
    LoggingProvider._is_configured = False

    # Reset the thread-local context
    if hasattr(_log_context, "correlation_id"):
        delattr(_log_context, "correlation_id")

    # Clean up handlers from the global logger to ensure test isolation
    logger = logging.getLogger("public_detective")
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    yield  # Test runs here

    # Post-test cleanup
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)


def test_get_logger_returns_singleton_instance(clean_logger):
    """
    Tests that get_logger returns the same logger instance on multiple calls.
    """
    provider = LoggingProvider()
    logger1 = provider.get_logger()
    logger2 = provider.get_logger()

    assert logger1 is logger2
    assert isinstance(logger1, logging.Logger)
    assert len(logger1.handlers) == 1


def test_configure_logger_is_idempotent(clean_logger):
    """
    Tests that calling _configure_logger multiple times covers the
    `if self._is_configured` branch and does not add more handlers.
    """
    provider = LoggingProvider()
    logger1 = provider._configure_logger()
    handlers_count1 = len(logger1.handlers)

    # Calling it again should hit the `if self._is_configured` branch and return early
    logger2 = provider._configure_logger()
    handlers_count2 = len(logger2.handlers)

    assert logger1 is logger2
    assert handlers_count1 == handlers_count2
    assert handlers_count1 == 1


def test_logger_does_not_add_handlers_if_already_present(clean_logger):
    """
    Tests that the provider does not add a new handler if the
    logger already has one when configuration is called.
    """
    logger = logging.getLogger("public_detective")
    mock_handler = MagicMock(spec=logging.Handler)
    mock_handler.level = logging.INFO
    logger.addHandler(mock_handler)

    # Trigger the configuration. Since a handler exists, it shouldn't add another.
    LoggingProvider()._configure_logger()

    assert len(logger.handlers) == 1
    assert logger.handlers[0] is mock_handler


def test_contextual_filter_adds_correlation_id(clean_logger):
    """Tests that the ContextualFilter adds the correlation_id to the log record."""
    log_filter = ContextualFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0, msg="", args=(), exc_info=None
    )

    # When correlation_id is not set
    log_filter.filter(record)
    assert record.correlation_id == "-"

    # When correlation_id is set
    correlation_id = str(uuid.uuid4())
    _log_context.correlation_id = correlation_id
    log_filter.filter(record)
    assert record.correlation_id == correlation_id


def test_set_correlation_id_context_manager(clean_logger):
    """
    Tests that the set_correlation_id context manager correctly sets and clears
    the correlation ID in the thread-local context.
    """
    provider = LoggingProvider()
    correlation_id = str(uuid.uuid4())

    assert not hasattr(_log_context, "correlation_id")

    with provider.set_correlation_id(correlation_id):
        assert _log_context.correlation_id == correlation_id

    assert _log_context.correlation_id is None


def test_set_correlation_id_clears_on_exception(clean_logger):
    """
    Tests that the correlation ID is cleared even if an exception occurs
    within the context manager.
    """
    provider = LoggingProvider()
    correlation_id = str(uuid.uuid4())

    with pytest.raises(ValueError, match="Test exception"):
        with provider.set_correlation_id(correlation_id):
            assert _log_context.correlation_id == correlation_id
            raise ValueError("Test exception")

    assert _log_context.correlation_id is None


@patch("providers.logging.ConfigProvider")
def test_logger_configuration_respects_log_level(mock_config_provider, clean_logger):
    """
    Tests that the logger is configured with the correct level from the config.
    """
    # Arrange: Configure the mock to return a specific log level
    mock_config = mock_config_provider.get_config.return_value
    mock_config.LOG_LEVEL = "DEBUG"

    # Act: Get the logger, which will trigger configuration
    logger = LoggingProvider().get_logger()

    # Assert: Check that the logger's level is set correctly
    assert logger.level == logging.DEBUG
