"""This module defines the configuration management for the application.

It uses Pydantic's BaseSettings to create a strongly-typed configuration
class that reads from environment variables and .env files. This ensures
all required configuration is present and valid at startup.
"""

from decimal import Decimal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

IBGE_CODE_SAO_PAULO = 3550308
IBGE_CODE_RIO_DE_JANEIRO = 3304557


class Config(BaseSettings):
    """A Pydantic model for managing application settings.

    It automatically loads configuration from environment variables and .env files.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    FORCE_SYNC: bool = False

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

    HTTP_REQUEST_DELAY_SECONDS: float = 0.5

    LOG_LEVEL: str = "INFO"

    TARGET_IBGE_CODES: list[int] = [
        IBGE_CODE_SAO_PAULO,
        IBGE_CODE_RIO_DE_JANEIRO,
    ]

    GCP_PROJECT: str = "public-detective"
    GCP_LOCATION: str = "us-central1"
    GCP_SERVICE_ACCOUNT_CREDENTIALS: str | None = None
    GCP_GCS_HOST: str | None = None
    GCP_GCS_BUCKET_PROCUREMENTS: str = "procurements"
    GCP_PUBSUB_HOST: str | None = None
    GCP_PUBSUB_TOPIC_PROCUREMENTS: str = "procurements"
    GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS: str | None = None
    GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS: str | None = None
    GCP_GEMINI_HOST: str | None = None
    GCP_GEMINI_MODEL: str = "gemini-2.5-pro"
    GCP_GEMINI_MAX_OUTPUT_TOKENS: int = 65535
    GCP_GEMINI_MAX_INPUT_TOKENS: int = 1048576
    GCP_GEMINI_TEXT_INPUT_COST: Decimal = Decimal("7.750969275")
    GCP_GEMINI_TEXT_INPUT_LONG_COST: Decimal = Decimal("15.50193855")
    GCP_GEMINI_TEXT_OUTPUT_COST: Decimal = Decimal("62.0077542")
    GCP_GEMINI_TEXT_OUTPUT_LONG_COST: Decimal = Decimal("93.0116313")
    GCP_GEMINI_THINKING_OUTPUT_COST: Decimal = Decimal("62.0077542")
    GCP_GEMINI_THINKING_OUTPUT_LONG_COST: Decimal = Decimal("93.0116313")
    GCP_GEMINI_AUDIO_INPUT_COST: Decimal = Decimal("7.750969275")
    GCP_GEMINI_AUDIO_INPUT_LONG_COST: Decimal = Decimal("15.50193855")
    GCP_GEMINI_IMAGE_INPUT_COST: Decimal = Decimal("7.750969275")
    GCP_GEMINI_IMAGE_INPUT_LONG_COST: Decimal = Decimal("15.50193855")
    GCP_GEMINI_VIDEO_INPUT_COST: Decimal = Decimal("7.750969275")
    GCP_GEMINI_VIDEO_INPUT_LONG_COST: Decimal = Decimal("15.50193855")
    GCP_GEMINI_THINKING_BUDGET: int = 32768

    WORKER_MAX_CONCURRENCY: int = 4

    RANKING_WEIGHT_IMPACT: float = 1.0
    RANKING_WEIGHT_QUALITY: float = 1.0
    RANKING_WEIGHT_COST: float = 0.1
    RANKING_WEIGHT_VOTES: float = 0.5
    RANKING_STABILITY_PERIOD_HOURS: int = 48
    RANKING_HIGH_IMPACT_KEYWORDS: list[str] = [
        "saúde",
        "hospitalar",
        "educação",
        "saneamento",
        "infraestrutura",
    ]
    RANKING_TEMPORAL_WINDOW_MIN_DAYS: int = 5
    RANKING_TEMPORAL_WINDOW_MAX_DAYS: int = 15
    RANKING_TEMPORAL_SCORE_THRESHOLD: int = 15

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
