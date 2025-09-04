import logging

from source.providers.logging import ContextualFilter, LoggingProvider


def test_contextual_filter_with_correlation_id():
    """
    Tests that the filter adds the correlation_id to the record when it's set.
    """
    filter = ContextualFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "", (), None)

    with LoggingProvider().set_correlation_id("test-id"):
        filter.filter(record)

    assert record.correlation_id == "test-id"


def test_contextual_filter_without_correlation_id():
    """
    Tests that the filter adds a default value when correlation_id is not set.
    """
    from source.providers.logging import _log_context

    if hasattr(_log_context, "correlation_id"):
        del _log_context.correlation_id

    filter = ContextualFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "", (), None)

    filter.filter(record)

    assert record.correlation_id == "-"
