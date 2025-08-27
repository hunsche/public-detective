from __future__ import annotations

import sys
from logging import Formatter, Logger, StreamHandler, _nameToLevel, getLogger

from providers.config import ConfigProvider


class LoggingProvider:
    """
    Provides a configured logger instance for the application using a
    Singleton pattern.

    This ensures that there is only one instance of the logger throughout the
    application's lifecycle, configured once based on settings from the config provider.
    """

    _instance: LoggingProvider | None = None
    _logger: Logger | None = None

    def __new__(cls):
        """
        Implements the Singleton pattern. If an instance does not exist, it creates one.
        Otherwise, it returns the existing instance.
        """
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _configure_logger(self) -> Logger:
        """
        Private method to configure the logger. This is called only once.
        """
        logger = getLogger("public_detective")

        if getattr(logger, "_configured", False):
            return logger

        config = ConfigProvider.get_config()
        log_level_str = config.LOG_LEVEL
        numeric_level = _nameToLevel.get(log_level_str.upper(), _nameToLevel["INFO"])
        logger.setLevel(numeric_level)

        if not logger.handlers:
            handler = StreamHandler(sys.stdout)
            formatter = Formatter(
                "%(asctime)s - %(name)s - [%(levelname)s] - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        setattr(logger, "_configured", True)
        logger.info(f"Logger configured with level: {log_level_str}")
        return logger

    def get_logger(self) -> Logger:
        """
        Returns the configured logger instance.

        If the logger has not been configured yet, this method will trigger
        the configuration. This lazy initialization ensures that the logger is
        only set up when it's first needed, preventing issues in test setups
        or module imports.
        """
        if not self._logger:
            self._logger = self._configure_logger()
        return self._logger
