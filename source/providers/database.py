import threading

from psycopg2.pool import ThreadedConnectionPool
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider


class DatabaseProvider:
    """
    Manages a thread-safe connection pool for PostgreSQL.
    Implements the Singleton pattern to ensure only one pool is created.
    """

    _pool: ThreadedConnectionPool | None = None
    _pool_creation_lock = threading.Lock()

    def __new__(cls):
        # This implementation of Singleton is not strictly necessary with the
        # get_pool class method, but it prevents accidental instantiation.
        if not hasattr(cls, "instance"):
            cls.instance = super(DatabaseProvider, cls).__new__(cls)
        return cls.instance

    @classmethod
    def get_pool(cls) -> ThreadedConnectionPool:
        """
        Retrieves a singleton instance of the PostgreSQL connection pool.
        If a pool does not exist, it creates a new one in a thread-safe manner.
        """
        if cls._pool is None:
            with cls._pool_creation_lock:
                if cls._pool is None:
                    logger: Logger = LoggingProvider.get_logger()
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
        """Closes all connections in the pool."""
        if cls._pool:
            logger: Logger = LoggingProvider.get_logger()
            logger.info("Closing all connections in the pool.")
            cls._pool.closeall()
            cls._pool = None
