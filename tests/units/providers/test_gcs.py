from unittest.mock import MagicMock, patch

import pytest
from google.auth.credentials import AnonymousCredentials
from providers.config import Config
from providers.gcs import GcsProvider


@pytest.fixture
def gcs_provider():
    """Fixture to create a GcsProvider instance."""
    with patch("providers.gcs.ConfigProvider"), patch("providers.gcs.LoggingProvider"):
        provider = GcsProvider()
        provider._client = None  # Ensure client is not cached
        return provider


@patch("google.cloud.storage.Client")
def test_create_client_with_emulator(mock_storage_client, gcs_provider):
    """
    Should create a GCS client with AnonymousCredentials when GCP_GCS_HOST is set.
    """
    config = Config(GCP_GCS_HOST="http://localhost:8086", GCP_PROJECT="test-project")

    gcs_provider._create_client(config)

    mock_storage_client.assert_called_once()
    _, kwargs = mock_storage_client.call_args
    assert isinstance(kwargs["credentials"], AnonymousCredentials)
    assert kwargs["project"] == "test-project"


@patch("google.cloud.storage.Client")
def test_create_client_for_production(mock_storage_client, gcs_provider):
    """
    Should create a GCS client with default credentials when GCP_GCS_HOST is not set.
    """
    config = Config(GCP_GCS_HOST=None, GCP_PROJECT="prod-project")

    gcs_provider._create_client(config)

    mock_storage_client.assert_called_once_with(project="prod-project")


@patch("providers.gcs.GcsProvider._create_client")
def test_get_or_create_client_caches_instance(mock_create_client, gcs_provider):
    """
    Should create a GCS client only once and then cache it.
    """
    client1 = gcs_provider._get_or_create_client()
    client2 = gcs_provider._get_or_create_client()

    mock_create_client.assert_called_once()
    assert client1 is client2


def test_upload_file_success(gcs_provider):
    """
    Should upload a file successfully and return its public URL.
    """
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.public_url = "http://fake-url/file.pdf"

    gcs_provider._get_or_create_client = MagicMock(return_value=mock_client)
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    public_url = gcs_provider.upload_file("test-bucket", "file.pdf", b"content", "application/pdf")

    mock_client.bucket.assert_called_once_with("test-bucket")
    mock_bucket.blob.assert_called_once_with("file.pdf")
    mock_blob.upload_from_string.assert_called_once_with(b"content", content_type="application/pdf")
    assert public_url == "http://fake-url/file.pdf"


def test_upload_file_failure(gcs_provider):
    """
    Should raise an exception when the upload fails.
    """
    mock_client = MagicMock()
    mock_client.bucket.side_effect = Exception("GCS Error")
    gcs_provider._get_or_create_client = MagicMock(return_value=mock_client)

    with pytest.raises(Exception, match="GCS Error"):
        gcs_provider.upload_file("test-bucket", "file.pdf", b"content", "application/pdf")
