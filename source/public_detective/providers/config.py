"""This module defines the configuration management for the application.

It uses Pydantic's BaseSettings to create a strongly-typed configuration
class that reads from environment variables and .env files. This ensures
all required configuration is present and valid at startup.
"""

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """A Pydantic model for managing application settings.

    It automatically loads configuration from environment variables and .env files.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    IS_DEBUG_MODE: bool = False

    POSTGRES_DRIVER: str = "postgresql"
    POSTGRES_ISOLATION_LEVEL: str = "AUTOCOMMIT"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "public_detective"
    POSTGRES_DB_SCHEMA: str | None = None

    PNCP_PUBLIC_QUERY_API_URL: str = "https://pncp.gov.br/api/consulta/v1/"
    PNCP_INTEGRATION_API_URL: str = "https://pncp.gov.br/api/pncp/v1/"

    LOG_LEVEL: str = "INFO"

    TARGET_IBGE_CODES: list[int] = [
        3550308,  # São Paulo
        3304557,  # Rio de Janeiro
    ]

    GCP_PROJECT: str = "public-detective"
    GCP_LOCATION: str = "us-central1"
    GCP_SERVICE_ACCOUNT_CREDENTIALS: str | None = None
    GCP_GCS_HOST: str | None = None
    GCP_GCS_BUCKET_PROCUREMENTS: str = "procurements"
    GCP_GCS_TEST_PREFIX: str | None = None
    GCP_PUBSUB_HOST: str | None = None
    GCP_PUBSUB_TOPIC_PROCUREMENTS: str = "procurements"
    GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS: str | None = None
    GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS: str | None = None
    GCP_GEMINI_HOST: str | None = None
    GCP_GEMINI_MODEL: str = "gemini-2.5-pro"
    GCP_GEMINI_MAX_OUTPUT_TOKENS: int = 8192
    GCP_GEMINI_PRICE_PER_1K_TOKENS: float = 0.002

    WORKER_MAX_CONCURRENCY: int = 4

    @model_validator(mode="after")
    def set_derived_pubsub_names(self) -> "Config":
        """Dynamically sets the DLQ topic and subscription names.

        This is done after the initial values have been loaded.

        Returns:
            The modified Config object.
        """
        if self.GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS is None:
            self.GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS = f"{self.GCP_PUBSUB_TOPIC_PROCUREMENTS}-dlq"

        if self.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS is None:
            self.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS = f"{self.GCP_PUBSUB_TOPIC_PROCUREMENTS}-subscription"

        return self


class ConfigProvider:
    """A provider class that acts as a factory for the application's configuration.

    It does not hold state but provides a method to create fresh config instances.
    """

    @staticmethod
    def get_config() -> Config:
        """Factory method that instantiates and returns a new Config object.

        Calling this function will always create a new instance of the Config model,
        which forces Pydantic to reload and re-validate all settings from the
        current environment variables. This ensures the configuration is always fresh.

        Returns:
            A new, validated Config object.
        """
        return Config()
