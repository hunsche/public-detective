"""This module provides a Google Cloud Storage (GCS) provider.

It encapsulates the logic for interacting with GCS, such as uploading
and downloading files.
"""

from typing import cast

from google.auth.credentials import AnonymousCredentials
from google.cloud.storage import Client
from public_detective.providers.config import ConfigProvider


class GcsProvider:
    """A provider for interacting with Google Cloud Storage."""

    _client: Client | None = None

    def get_client(self) -> Client:
        """Returns a GCS client, creating one if it doesn't exist.

        Returns:
            A GCS client.
        """
        if not self._client:
            config = ConfigProvider.get_config()
            if config.GCP_GCS_HOST:
                self._client = Client(
                    credentials=AnonymousCredentials(),
                    project="test",
                    client_options={"api_endpoint": config.GCP_GCS_HOST},
                )
            else:
                self._client = Client()
        return self._client

    def upload_file(
        self,
        bucket_name: str,
        destination_blob_name: str,
        content: bytes,
        content_type: str,
    ) -> None:
        """Uploads a file to a GCS bucket.

        Args:
            bucket_name: The name of the GCS bucket.
            destination_blob_name: The name of the blob to create.
            content: The content of the file to upload.
            content_type: The content type of the file.
        """
        client = self.get_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_string(content, content_type=content_type)

    def download_file(self, bucket_name: str, source_blob_name: str) -> bytes:
        """Downloads a file from a GCS bucket.

        Args:
            bucket_name: The name of the GCS bucket.
            source_blob_name: The name of the blob to download.

        Returns:
            The content of the downloaded file.
        """
        client = self.get_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(source_blob_name)
        return cast(bytes, blob.download_as_bytes())
