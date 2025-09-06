"""This module provides a singleton database connection manager for the application."""

import threading

from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


class DatabaseManager:
    """Manages a thread-safe connection pool for PostgreSQL using SQLAlchemy.

    This class implements the Singleton pattern to ensure that only one
    instance of the connection engine is created and shared across the
    application.
    """

    _engine: Engine | None = None
    _engine_creation_lock = threading.Lock()

    def __new__(cls) -> "DatabaseManager":
        """Ensures that only one instance of this class can be created.

        Returns:
            The singleton instance of the DatabaseManager.
        """
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    @classmethod
    def get_engine(cls) -> Engine:
        """Retrieves a singleton instance of the SQLAlchemy engine.

        Returns:
            The singleton instance of the SQLAlchemy engine.
        """
        if cls._engine is None:
            with cls._engine_creation_lock:
                if cls._engine is None:
                    logger: Logger = LoggingProvider().get_logger()
                    logger.info("Database engine not found, creating new instance...")
                    config: Config = ConfigProvider.get_config()

                    url = (
                        f"{config.POSTGRES_DRIVER}://"
                        f"{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}@"
                        f"{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/"
                        f"{config.POSTGRES_DB}"
                    )

                    connect_args = {}
                    if config.POSTGRES_DB_SCHEMA:
                        logger.info(f"Using isolated schema: {config.POSTGRES_DB_SCHEMA}")
                        connect_args["options"] = f"-csearch_path={config.POSTGRES_DB_SCHEMA}"

                    cls._engine = create_engine(
                        url,
                        pool_size=10,
                        max_overflow=20,
                        connect_args=connect_args,
                    )
                    logger.info("SQLAlchemy engine created successfully.")
        return cls._engine

    @classmethod
    def release_engine(cls) -> None:
        """Disposes of the engine's connection pool and resets the singleton instance."""
        if cls._engine:
            logger: Logger = LoggingProvider().get_logger()
            logger.info("Disposing of the database engine.")
            cls._engine.dispose()
            cls._engine = None
