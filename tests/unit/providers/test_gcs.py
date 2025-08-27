from unittest.mock import MagicMock, patch

from google.auth.credentials import AnonymousCredentials
from providers.gcs import GcsProvider


@patch("providers.gcs.GcsProvider.__init__", lambda x: None)
def test_get_or_create_client_with_emulator():
    """
    Should create a GCS client with AnonymousCredentials when GCP_GCS_HOST is set.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config.GCP_GCS_HOST = "http://localhost:8086"
    mock_config.GCP_PROJECT = "test-project"

    gcs_provider = GcsProvider()
    gcs_provider.config = mock_config
    gcs_provider.logger = MagicMock()
    gcs_provider._client_creation_lock = MagicMock()
    gcs_provider._client = None  # Ensure client is recreated

    with patch("google.cloud.storage.Client") as mock_storage_client:
        # Act
        client = gcs_provider._get_or_create_client()

        # Assert
        mock_storage_client.assert_called_once()
        _, kwargs = mock_storage_client.call_args
        assert isinstance(kwargs["credentials"], AnonymousCredentials)
        assert kwargs["project"] == "test-project"
        assert client is not None


@patch("providers.gcs.GcsProvider.__init__", lambda x: None)
def test_get_or_create_client_for_production():
    """
    Should create a GCS client with default credentials when GCP_GCS_HOST is not set.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config.GCP_GCS_HOST = None  # Emulator is not set
    mock_config.GCP_PROJECT = "prod-project"

    gcs_provider = GcsProvider()
    gcs_provider.config = mock_config
    gcs_provider.logger = MagicMock()
    gcs_provider._client_creation_lock = MagicMock()
    gcs_provider._client = None  # Ensure client is recreated

    with patch("google.cloud.storage.Client") as mock_storage_client:
        # Act
        client = gcs_provider._get_or_create_client()

        # Assert
        mock_storage_client.assert_called_once_with(project="prod-project")
        assert client is not None


@patch("providers.gcs.GcsProvider.__init__", lambda x: None)
def test_get_or_create_client_caches_instance():
    """
    Should create a GCS client only once and then cache it.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config.GCP_GCS_HOST = None
    mock_config.GCP_PROJECT = "prod-project"

    gcs_provider = GcsProvider()
    gcs_provider.config = mock_config
    gcs_provider.logger = MagicMock()
    gcs_provider._client_creation_lock = MagicMock()
    gcs_provider._client = None

    with patch("google.cloud.storage.Client") as mock_storage_client:
        # Act
        client1 = gcs_provider._get_or_create_client()
        client2 = gcs_provider._get_or_create_client()

        # Assert
        mock_storage_client.assert_called_once()
        assert client1 is client2


@patch("providers.gcs.GcsProvider.__init__", lambda x: None)
def test_upload_file_success():
    """
    Should upload a file successfully and return its public URL.
    """
    # Arrange
    gcs_provider = GcsProvider()
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.public_url = "http://fake-url/file.pdf"

    gcs_provider._get_or_create_client = MagicMock(return_value=mock_client)
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob
    gcs_provider.logger = MagicMock()

    # Act
    public_url = gcs_provider.upload_file("test-bucket", "file.pdf", b"content", "application/pdf")

    # Assert
    mock_client.bucket.assert_called_once_with("test-bucket")
    mock_bucket.blob.assert_called_once_with("file.pdf")
    mock_blob.upload_from_string.assert_called_once_with(b"content", content_type="application/pdf")
    assert public_url == "http://fake-url/file.pdf"


import pytest

@patch("providers.gcs.GcsProvider.__init__", lambda x: None)
def test_upload_file_failure():
    """
    Should raise an exception when the upload fails.
    """
    # Arrange
    gcs_provider = GcsProvider()
    mock_client = MagicMock()
    mock_client.bucket.side_effect = Exception("GCS Error")
    gcs_provider._get_or_create_client = MagicMock(return_value=mock_client)
    gcs_provider.logger = MagicMock()

    # Act & Assert
    with pytest.raises(Exception, match="GCS Error"):
        gcs_provider.upload_file("test-bucket", "file.pdf", b"content", "application/pdf")
