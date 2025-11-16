"""This module provides a Google Cloud Storage (GCS) provider.

It encapsulates the logic for interacting with GCS, such as uploading
and downloading files.
"""
import json
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
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
            if config.STORAGE_EMULATOR_HOST:
                self._client = Client(
                    credentials=AnonymousCredentials(),
                    project=config.GCP_PROJECT,
                )
            else:
                self._client = Client(project=config.GCP_PROJECT)
        return self._client

    def upload_file(
        self,
        bucket_name: str,
        destination_blob_name: str,
        content: bytes,
        content_type: str,
        *,
        metadata: dict | None = None,
    ) -> None:
        """Uploads a file to a GCS bucket.

        Args:
            bucket_name: The name of the GCS bucket.
            destination_blob_name: The name of the blob to create.
            content: The content of the file to upload.
            content_type: The content type of the file.
            metadata: Optional metadata to attach to the GCS object.
        """
        config = ConfigProvider.get_config()
        # Use a simple requests POST for the emulator, as the client library
        # has issues with fake-gcs-server.
        if config.STORAGE_EMULATOR_HOST:
            related = MIMEMultipart('related')

            metadata_part = MIMEApplication(json.dumps({'name': destination_blob_name, 'metadata': metadata}), 'json', _encoder=lambda x: x)
            metadata_part.add_header('Content-Type', 'application/json; charset=UTF-8')
            related.attach(metadata_part)

            media_part = MIMEApplication(content, _encoder=lambda x: x)
            media_part.add_header('Content-Type', content_type)
            related.attach(media_part)

            body = related.as_string().split('\n\n', 1)[1]
            headers = {'Content-Type': related.get('Content-Type')}

            url = f"{config.STORAGE_EMULATOR_HOST}/upload/storage/v1/b/{bucket_name}/o?uploadType=multipart"
            response = requests.post(url, data=body, headers=headers, timeout=10)
            response.raise_for_status()
        else:
            client = self.get_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)

            if metadata:
                blob.metadata = metadata

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

    def list_blobs(self, bucket_name: str, prefix: str | None = None) -> list:
        """Lists all the blobs in the bucket with a given prefix.

        Args:
            bucket_name: The name of the GCS bucket.
            prefix: The prefix to filter the blobs.

        Returns:
            A list of blobs.
        """
        client = self.get_client()
        bucket = client.bucket(bucket_name)
        return list(bucket.list_blobs(prefix=prefix))
