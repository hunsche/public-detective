from unittest.mock import MagicMock, patch

import pytest
from public_detective.providers.gcs import GcsProvider


@patch("public_detective.providers.gcs.Client")
def test_get_client_caches_instance(mock_storage_client: MagicMock) -> None:
    """
    Should create a GCS client only once and then cache it.
    """
    # Arrange
    gcs_provider = GcsProvider()
    gcs_provider._client = None  # Ensure client is not cached

    # Act
    client1 = gcs_provider.get_client()
    client2 = gcs_provider.get_client()

    # Assert
    mock_storage_client.assert_called_once()
    assert client1 is client2


def test_upload_file_success() -> None:
    """
    Should upload a file successfully.
    """
    # Arrange
    gcs_provider = GcsProvider()
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()

    gcs_provider._client = mock_client
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    # Act
    gcs_provider.upload_file("test-bucket", "file.pdf", b"content", "application/pdf")

    # Assert
    mock_client.bucket.assert_called_once_with("test-bucket")
    mock_bucket.blob.assert_called_once_with("file.pdf")
    mock_blob.upload_from_string.assert_called_once_with(b"content", content_type="application/pdf")


def test_upload_file_failure() -> None:
    """
    Should raise an exception when the upload fails.
    """
    # Arrange
    gcs_provider = GcsProvider()
    mock_client = MagicMock()
    mock_client.bucket.side_effect = Exception("GCS Error")
    gcs_provider._client = mock_client

    # Act & Assert
    with pytest.raises(Exception, match="GCS Error"):
        gcs_provider.upload_file("test-bucket", "file.pdf", b"content", "application/pdf")


def test_download_file_success() -> None:
    """
    Should download a file successfully.
    """
    # Arrange
    gcs_provider = GcsProvider()
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.download_as_bytes.return_value = b"file content"

    gcs_provider._client = mock_client
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    # Act
    content = gcs_provider.download_file("test-bucket", "file.pdf")

    # Assert
    mock_client.bucket.assert_called_once_with("test-bucket")
    mock_bucket.blob.assert_called_once_with("file.pdf")
    assert content == b"file content"


def test_download_file_failure() -> None:
    """
    Should raise an exception when the download fails.
    """
    # Arrange
    gcs_provider = GcsProvider()
    mock_client = MagicMock()
    mock_client.bucket.side_effect = Exception("GCS Error")
    gcs_provider._client = mock_client

    # Act & Assert
    with pytest.raises(Exception, match="GCS Error"):
        gcs_provider.download_file("test-bucket", "file.pdf")


@patch("public_detective.providers.gcs.ConfigProvider")
@patch("public_detective.providers.gcs.Client")
def test_get_client_real_credentials(mock_gcs_client: MagicMock, mock_config_provider: MagicMock) -> None:
    """Tests that a real GCS client is created when no host is configured."""
    mock_config = MagicMock()
    mock_config.GCP_GCS_HOST = None
    mock_config_provider.get_config.return_value = mock_config

    # Ensure the class-level client is reset before the test
    GcsProvider._client = None

    provider = GcsProvider()
    client = provider.get_client()

    mock_gcs_client.assert_called_once_with()
    assert client is not None
