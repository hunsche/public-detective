from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """
    Pydantic model that defines and validates all application settings.

    It automatically reads from environment variables or a .env file,
    providing type validation and default values.
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
        # 3304557,  # Rio de Janeiro
        # 3106200,  # Belo Horizonte
        # 3518800,  # Campinas
        # 4205407,  # Florianópolis
        # 4314902,  # Porto Alegre
        # 5208707,  # Goiânia
        # 2927408,  # Salvador
    ]

    GCP_PROJECT: str = "public-detective"
    GCP_GCS_BUCKET_PROCUREMENTS: str = "procurements"
    GCP_GCS_HOST: str | None = None
    GCP_GCS_TEST_PREFIX: str | None = None
    GCP_PUBSUB_TOPIC_PROCUREMENTS: str = "procurements"
    GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS: str | None = None
    GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS: str | None = None
    GCP_PUBSUB_HOST: str | None = None
    GCP_GEMINI_API_KEY: str | None = None
    GCP_GEMINI_MODEL: str = "gemini-2.5-pro"

    @model_validator(mode="after")
    def set_derived_pubsub_names(self) -> "Config":
        """
        Dynamically sets the DLQ topic and subscription names
        after the initial values have been loaded.
        """
        if self.GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS is None:
            self.GCP_PUBSUB_TOPIC_DLQ_PROCUREMENTS = f"{self.GCP_PUBSUB_TOPIC_PROCUREMENTS}-dlq"

        if self.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS is None:
            self.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS = f"{self.GCP_PUBSUB_TOPIC_PROCUREMENTS}-subscription"

        return self


class ConfigProvider:
    """
    A provider class that acts as a factory for the application's configuration.
    It does not hold state but provides a method to create fresh config instances.
    """

    @staticmethod
    def get_config() -> Config:
        """
        Factory method that instantiates and returns a new Config object.

        Calling this function will always create a new instance of the Config model,
        which forces Pydantic to reload and re-validate all settings from the
        current environment variables. This ensures the configuration is always fresh.

        :return: A new, validated Config object.
        """
        return Config()
