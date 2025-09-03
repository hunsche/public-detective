from unittest.mock import MagicMock, patch

import pytest
from google.auth.credentials import AnonymousCredentials
from providers.gcs import GcsProvider


@patch("providers.gcs.ConfigProvider")
@patch("providers.gcs.LoggingProvider")
def test_get_or_create_client_with_emulator(mock_logging_provider, mock_config_provider):
    """
    Should create a GCS client with AnonymousCredentials when GCP_GCS_HOST is set.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config.GCP_GCS_HOST = "http://localhost:8086"
    mock_config.GCP_PROJECT = "test-project"
    mock_config_provider.get_config.return_value = mock_config

    mock_logger = MagicMock()
    mock_logging_provider.get_logger.return_value = mock_logger

    with patch("google.cloud.storage.Client") as mock_storage_client:
        # Act
        provider = GcsProvider()
        client = provider._get_or_create_client()

        # Assert
        mock_storage_client.assert_called_once()
        _, kwargs = mock_storage_client.call_args
        assert isinstance(kwargs["credentials"], AnonymousCredentials)
        assert kwargs["project"] == "test-project"
        assert client is not None


@patch("providers.gcs.ConfigProvider")
@patch("providers.gcs.LoggingProvider")
def test_get_or_create_client_for_production(mock_logging_provider, mock_config_provider):
    """
    Should create a GCS client with default credentials when GCP_GCS_HOST is not set.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config.GCP_GCS_HOST = None  # Emulator is not set
    mock_config.GCP_PROJECT = "prod-project"
    mock_config_provider.get_config.return_value = mock_config

    mock_logger = MagicMock()
    mock_logging_provider.get_logger.return_value = mock_logger

    with patch("google.cloud.storage.Client") as mock_storage_client:
        # Act
        provider = GcsProvider()
        client = provider._get_or_create_client()

        # Assert
        mock_storage_client.assert_called_once_with(project="prod-project")
        assert client is not None


@patch("providers.gcs.ConfigProvider")
@patch("providers.gcs.LoggingProvider")
def test_get_or_create_client_caches_instance(mock_logging_provider, mock_config_provider):
    """
    Should create a GCS client only once and then cache it.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config.GCP_GCS_HOST = None
    mock_config.GCP_PROJECT = "prod-project"
    mock_config_provider.get_config.return_value = mock_config

    mock_logger = MagicMock()
    mock_logging_provider.get_logger.return_value = mock_logger

    with patch("google.cloud.storage.Client") as mock_storage_client:
        # Act
        provider = GcsProvider()
        client1 = provider._get_or_create_client()
        client2 = provider._get_or_create_client()

        # Assert
        mock_storage_client.assert_called_once()
        assert client1 is client2


@patch("providers.gcs.ConfigProvider")
@patch("providers.gcs.LoggingProvider")
def test_upload_file_success(mock_logging_provider, mock_config_provider):
    """
    Should upload a file successfully and return its public URL.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config_provider.get_config.return_value = mock_config
    mock_logger = MagicMock()
    mock_logging_provider.get_logger.return_value = mock_logger

    provider = GcsProvider()
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.public_url = "http://fake-url/file.pdf"

    provider._get_or_create_client = MagicMock(return_value=mock_client)
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    # Act
    public_url = provider.upload_file("test-bucket", "file.pdf", b"content", "application/pdf")

    # Assert
    mock_client.bucket.assert_called_once_with("test-bucket")
    mock_bucket.blob.assert_called_once_with("file.pdf")
    mock_blob.upload_from_string.assert_called_once_with(b"content", content_type="application/pdf")
    assert public_url == "http://fake-url/file.pdf"


@patch("providers.gcs.ConfigProvider")
@patch("providers.gcs.LoggingProvider")
def test_upload_file_failure(mock_logging_provider, mock_config_provider):
    """
    Should raise an exception when the upload fails.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config_provider.get_config.return_value = mock_config
    mock_logger = MagicMock()
    mock_logging_provider.get_logger.return_value = mock_logger

    provider = GcsProvider()
    mock_client = MagicMock()
    mock_client.bucket.side_effect = Exception("GCS Error")
    provider._get_or_create_client = MagicMock(return_value=mock_client)

    # Act & Assert
    with pytest.raises(Exception, match="GCS Error"):
        provider.upload_file("test-bucket", "file.pdf", b"content", "application/pdf")
