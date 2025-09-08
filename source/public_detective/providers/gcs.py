import json
import os
import threading
from typing import cast

from google.cloud import storage
from public_detective.providers.config import Config, ConfigProvider
from public_detective.providers.logging import Logger, LoggingProvider


class GcsProvider:
    """Provides methods to interact with Google Cloud Storage (GCS).

    This provider centralizes client management and abstracts away the
    details of uploading files to a GCS bucket in a thread-safe manner. It
    automatically configures itself to use a local GCS emulator if the
    GCP_GCS_HOST environment variable is set.
    """

    _client: storage.Client | None = None
    _client_creation_lock: threading.Lock
    logger: Logger
    config: Config

    def __init__(self) -> None:
        """Initializes the GcsProvider.

        This constructor sets up the logger, loads the application
        configuration, and initializes a thread-safe lock for client
        creation.
        """
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()
        self._client_creation_lock = threading.Lock()

    def _get_or_create_client(self) -> storage.Client:
        """Retrieves a singleton instance of the GCS Client.

        If a client instance does not exist, it creates a new one in a
        thread-safe manner. The initialization priority is as follows:
        1. GCS Emulator: If GCP_GCS_HOST is set, it will always be used.
        2. Service Account JSON: If GCP_SERVICE_ACCOUNT_CREDENTIALS has JSON
           content, it will be used.
        3. Application Default Credentials (ADC): As a final fallback.

        Returns:
            A singleton instance of google.cloud.storage.Client.
        """
        if self._client is None:
            with self._client_creation_lock:
                if self._client is None:
                    self.logger.info("GCS client not found in cache, creating new instance...")

                    credentials_value = self.config.GCP_SERVICE_ACCOUNT_CREDENTIALS
                    emulator_host = self.config.GCP_GCS_HOST

                    # Priority 1: Use Emulator if GCP_GCS_HOST is set
                    if emulator_host:
                        from google.auth.credentials import AnonymousCredentials

                        os.environ["STORAGE_EMULATOR_HOST"] = emulator_host
                        self.logger.info(f"GCS client configured for emulator at {emulator_host}")
                        self._client = storage.Client(
                            credentials=AnonymousCredentials(), project=self.config.GCP_PROJECT
                        )
                    # Priority 2: Use Service Account JSON from env var
                    elif credentials_value:
                        try:
                            if credentials_value.strip().startswith("{"):
                                self.logger.info("GCS client configured from Service Account JSON string.")
                                credentials_info = json.loads(credentials_value)
                                self._client = storage.Client.from_service_account_info(
                                    credentials_info, project=self.config.GCP_PROJECT
                                )
                            else:
                                raise ValueError(
                                    "GCP_SERVICE_ACCOUNT_CREDENTIALS is set but does not appear to be a JSON object."
                                )
                        except json.JSONDecodeError as e:
                            self.logger.error(f"Failed to parse GCP credentials JSON: {e}")
                            raise ValueError("Invalid JSON in GCP_SERVICE_ACCOUNT_CREDENTIALS.") from e
                    # Priority 3: Fallback to Application Default Credentials
                    else:
                        self.logger.info(
                            "GCS client configured for Google Cloud production via Application Default Credentials."
                        )
                        self._client = storage.Client(project=self.config.GCP_PROJECT)

                    self.logger.info("GCS client created successfully.")
        return cast(storage.Client, self._client)

    def upload_file(self, bucket_name: str, destination_blob_name: str, content: bytes, content_type: str) -> str:
        """Uploads byte content to a specified GCS bucket.

        Args:
            bucket_name: The name of the GCS bucket.
            destination_blob_name: The desired name for the object in the bucket.
            content: The raw byte content of the file to upload.
            content_type: The MIME type of the content (e.g., 'application/pdf').

        Returns:
            The public URL of the uploaded file.

        Raises:
            Exception: If the upload process fails.
        """
        try:
            client = self._get_or_create_client()
            bucket = client.bucket(bucket_name)

            blob = bucket.blob(destination_blob_name)

            self.logger.info(f"Uploading file to GCS: gs://{bucket_name}/{destination_blob_name}")

            blob.upload_from_string(content, content_type=content_type)

            self.logger.info("File uploaded successfully.")
            return str(blob.public_url)
        except Exception as e:
            self.logger.error(f"Failed to upload file to GCS bucket '{bucket_name}': {e}")
            raise
