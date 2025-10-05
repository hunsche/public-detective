"""This module sets up a centralized, context-aware logging system.

It provides a `LoggingProvider` singleton that configures and dispenses a
logger. A key feature is the `ContextualFilter`, which uses thread-local
storage to inject a `correlation_id` into every log message, making it
easier to trace requests or tasks as they flow through the application.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Generator
from contextlib import contextmanager
from logging import Filter, Formatter, Logger, LogRecord, StreamHandler, _nameToLevel, getLogger

from public_detective.providers.config import ConfigProvider

_log_context = threading.local()


class ContextualFilter(Filter):
    """A logging filter that makes a correlation ID available to the log formatter."""

    def filter(self, record: LogRecord) -> bool:
        """Adds the correlation ID to the log record from thread-local context.

        Args:
            record: The log record to be filtered.

        Returns:
            Always True to ensure the log record is processed.
        """
        record.correlation_id = getattr(_log_context, "correlation_id", "-")
        return True


class LoggingProvider:
    """Provides a configured logger instance for the application.

    This class uses a Singleton pattern to ensure that there is only one
    instance of the logger throughout the application's lifecycle, configured
    once based on settings from the config provider.
    """

    _instance: LoggingProvider | None = None
    _logger: Logger | None = None
    _is_configured: bool = False

    def __new__(cls) -> LoggingProvider:
        """Implements the Singleton pattern.

        If an instance does not exist, it creates one. Otherwise, it returns
        the existing instance.

        Returns:
            The singleton instance of the LoggingProvider.
        """
        if not cls._instance:  # pragma: no cover
            cls._instance = super().__new__(cls)
        return cls._instance

    def _configure_logger(self) -> Logger:
        """Private method to configure the logger. This is called only once.

        Returns:
            The configured logger instance.
        """
        logger = getLogger("public_detective")

        if self._is_configured:  # pragma: no cover
            return logger

        config = ConfigProvider.get_config()
        log_level_str = config.LOG_LEVEL
        numeric_level = _nameToLevel.get(log_level_str.upper(), _nameToLevel["INFO"])
        logger.setLevel(numeric_level)

        if not logger.handlers:
            handler = StreamHandler(sys.stderr)
            formatter = Formatter(
                "%(asctime)s - %(name)s - [%(levelname)s] [%(correlation_id)s] - " "%(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.addFilter(ContextualFilter())

        self._is_configured = True
        logger.info(f"Logger configured with level: {log_level_str}")
        return logger

    def get_logger(self) -> Logger:
        """Returns the configured logger instance.

        If the logger has not been configured yet, this method will trigger
        the configuration. This lazy initialization ensures that the logger is
        only set up when it's first needed, preventing issues in test setups
        or module imports.

        Returns:
            The configured logger instance.
        """
        if not self._logger:
            self._logger = self._configure_logger()
        return self._logger

    @contextmanager
    def set_correlation_id(self, correlation_id: str) -> Generator[None, None, None]:
        """A context manager to set and automatically clear the correlation ID.

        Args:
            correlation_id: The correlation ID to set for the context.

        Yields:
            None.
        """
        try:
            _log_context.correlation_id = correlation_id
            yield
        finally:
            _log_context.correlation_id = None
