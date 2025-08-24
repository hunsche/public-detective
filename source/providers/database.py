"""
This module provides a singleton database connection pool for the application.
"""

import threading

from psycopg2.pool import ThreadedConnectionPool
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider


class DatabaseProvider:
    """
    Manages a thread-safe connection pool for PostgreSQL.

    This class implements the Singleton pattern to ensure that only one
    instance of the connection pool is created and shared across the
    application.
    """

    _pool: ThreadedConnectionPool | None = None
    _pool_creation_lock = threading.Lock()

    def __new__(cls):
        """
        Ensures that only one instance of this class can be created.
        """
        if not hasattr(cls, "instance"):
            cls.instance = super(DatabaseProvider, cls).__new__(cls)
        return cls.instance

    @classmethod
    def get_pool(cls) -> ThreadedConnectionPool:
        """
        Retrieves a singleton instance of the PostgreSQL connection pool.
        """
        if cls._pool is None:
            with cls._pool_creation_lock:
                if cls._pool is None:
                    logger: Logger = LoggingProvider().get_logger()
                    logger.info("Connection pool not found, creating new instance...")
                    config: Config = ConfigProvider.get_config()

                    cls._pool = ThreadedConnectionPool(
                        minconn=1,
                        maxconn=10,
                        dbname=config.POSTGRES_DB,
                        user=config.POSTGRES_USER,
                        password=config.POSTGRES_PASSWORD,
                        host=config.POSTGRES_HOST,
                        port=config.POSTGRES_PORT,
                    )
                    logger.info("PostgreSQL connection pool created successfully.")
        return cls._pool

    @classmethod
    def release_pool(cls) -> None:
        """
        Closes all connections in the pool and resets the singleton instance.
        """
        if cls._pool:
            logger: Logger = LoggingProvider().get_logger()
            logger.info("Closing all connections in the pool.")
            cls._pool.closeall()
            cls._pool = None
