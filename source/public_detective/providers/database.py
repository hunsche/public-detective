"""This module provides a singleton database connection manager for the application."""

import threading

from google.cloud.sql.connector import Connector, IPTypes
from pg8000.dbapi import Connection
from public_detective.providers.config import Config, ConfigProvider
from public_detective.providers.logging import Logger, LoggingProvider
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


class DatabaseManager:
    """Manages a thread-safe connection pool for PostgreSQL using SQLAlchemy.

    Now supports Google Cloud SQL Connector for IAM Authentication.
    """

    _engine: Engine | None = None
    _engine_creation_lock = threading.Lock()
    _connector: Connector | None = None

    def __new__(cls) -> "DatabaseManager":
        """Ensures that only one instance of this class can be created.

        Returns:
            The singleton instance of the DatabaseManager.
        """
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    @classmethod
    def _get_google_connector(cls) -> Connector:
        """Initializes the Google Cloud SQL Connector lazily.

        Returns:
            Connector: The Google Cloud SQL Connector instance.
        """
        if cls._connector is None:
            cls._connector = Connector()
        return cls._connector

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
                    config: Config = ConfigProvider.get_config()

                    use_cloud_sql = getattr(config, "USE_CLOUD_SQL_AUTH", False)

                    if use_cloud_sql:
                        logger.info("Initializing database engine using Cloud SQL Connector (IAM)...")

                        connector = cls._get_google_connector()

                        def getconn() -> Connection:
                            """Returns a pg8000 connection object.

                            Returns:
                                Connection: A pg8000 connection object.
                            """
                            conn = connector.connect(
                                config.INSTANCE_CONNECTION_NAME,
                                "pg8000",
                                user=config.POSTGRES_USER,
                                db=config.POSTGRES_DB,
                                enable_iam_auth=True,
                                ip_type=IPTypes.PRIVATE,
                            )
                            return conn

                        cls._engine = create_engine(
                            "postgresql+pg8000://",
                            creator=getconn,
                            pool_size=10,
                            max_overflow=20,
                            pool_timeout=30,
                            pool_recycle=1800,
                            pool_pre_ping=True,
                        )

                    else:
                        logger.info("Initializing database engine using Standard TCP (Legacy)...")
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
        logger: Logger = LoggingProvider().get_logger()
        if cls._engine:
            logger.info("Disposing of the database engine.")
            cls._engine.dispose()
            cls._engine = None

        if cls._connector:
            logger.info("Closing Cloud SQL Connector.")
            cls._connector.close()
            cls._connector = None
