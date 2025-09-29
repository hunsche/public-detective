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


@patch("public_detective.providers.gcs.Client")
@patch("public_detective.providers.gcs.ConfigProvider")
def test_get_client_no_host(mock_config_provider: MagicMock, mock_storage_client: MagicMock) -> None:
    """
    Tests that the GCS client is created without special options when no host is configured.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config.GCP_GCS_HOST = None
    mock_config_provider.get_config.return_value = mock_config

    gcs_provider = GcsProvider()
    gcs_provider._client = None  # Ensure client is not cached

    # Act
    gcs_provider.get_client()

    # Assert
    mock_storage_client.assert_called_once_with()
