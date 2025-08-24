import os
import threading
from typing import cast

from google.cloud import storage
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider


class GcsProvider:
    """Provides static methods to interact with Google Cloud Storage (GCS).

    This provider centralizes client management and abstracts away the
    details of uploading files to a GCS bucket in a thread-safe manner. It
    automatically configures itself to use a local GCS emulator if the
    GCP_GCS_HOST environment variable is set.
    """

    logger: Logger = LoggingProvider().get_logger()
    config: Config = ConfigProvider.get_config()

    _client: storage.Client | None = None
    _client_creation_lock = threading.Lock()

    @staticmethod
    def _get_or_create_client() -> storage.Client:
        """Retrieves a singleton instance of the GCS Client.

        If a client instance does not exist, it creates a new one in a
        thread-safe manner, caches it, and then returns it. It also handles
        the setup for the GCS emulator.

        Returns:
            A singleton instance of google.cloud.storage.Client.
        """
        if GcsProvider._client is None:
            with GcsProvider._client_creation_lock:
                if GcsProvider._client is None:
                    GcsProvider.logger.info("GCS client not found in cache, creating new instance...")

                    emulator_host = GcsProvider.config.GCP_GCS_HOST
                    if emulator_host:
                        os.environ["STORAGE_EMULATOR_HOST"] = emulator_host
                        GcsProvider.logger.info(f"GCS client configured for emulator at {emulator_host}")
                        GcsProvider._client = storage.Client()
                    else:
                        GcsProvider.logger.info("GCS client configured for Google Cloud production.")
                        GcsProvider._client = storage.Client(project=GcsProvider.config.GCP_PROJECT)

                    GcsProvider.logger.info("GCS client created successfully.")
        return cast(storage.Client, GcsProvider._client)

    @staticmethod
    def upload_file(bucket_name: str, destination_blob_name: str, content: bytes, content_type: str) -> str:
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
            client = GcsProvider._get_or_create_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)

            GcsProvider.logger.info(f"Uploading file to GCS: gs://{bucket_name}/{destination_blob_name}")

            blob.upload_from_string(content, content_type=content_type)

            GcsProvider.logger.info("File uploaded successfully.")
            return str(blob.public_url)
        except Exception as e:
            GcsProvider.logger.error(f"Failed to upload file to GCS bucket '{bucket_name}': {e}")
            raise
