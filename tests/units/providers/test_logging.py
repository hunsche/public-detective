"""
Unit tests for the LoggingProvider.
"""

from providers.logging import LoggingProvider


def test_logging_provider_is_singleton():
    """
    Tests that the LoggingProvider follows the Singleton pattern.
    """
    instance1 = LoggingProvider()
    instance2 = LoggingProvider()
    assert instance1 is instance2


def test_correlation_id_context_manager():
    """
    Tests that the correlation ID is correctly set and cleared.
    """
    provider = LoggingProvider()
    with provider.set_correlation_id("test-id"):
        # We need to access the internal _log_context for testing, which is acceptable for unit tests.
        from providers.logging import _log_context

        assert _log_context.correlation_id == "test-id"

    assert not hasattr(_log_context, "correlation_id") or _log_context.correlation_id is None
