"""This module contains tests for the GcsProvider."""
from unittest.mock import MagicMock, patch

import pytest
from public_detective.providers.gcs import GcsProvider


@patch("public_detective.providers.gcs.ConfigProvider")
def test_upload_file_success_emulator(mock_config_provider):
    """Should use requests to upload a file when STORAGE_EMULATOR_HOST is set."""
    # Arrange
    mock_config_provider.get_config.return_value.STORAGE_EMULATOR_HOST = "http://localhost:8086"
    gcs_provider = GcsProvider()

    # Act
    with patch("requests.post") as mock_post:
        gcs_provider.upload_file("test-bucket", "file.pdf", b"content", "application/pdf")

        # Assert
        mock_post.assert_called_once()
        call_args, call_kwargs = mock_post.call_args
        assert "http://localhost:8086/upload/storage/v1/b/test-bucket/o" in call_args[0]
        # Check that the content is in the multipart data
        assert "content" in call_kwargs["data"]


@patch("public_detective.providers.gcs.ConfigProvider")
def test_upload_file_success_production(mock_config_provider):
    """Should use the GCS client to upload a file in a production environment."""
    # Arrange
    mock_config_provider.get_config.return_value.STORAGE_EMULATOR_HOST = None
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


@patch("public_detective.providers.gcs.ConfigProvider")
def test_upload_file_failure(mock_config_provider):
    """Should raise an exception when the upload fails."""
    # Arrange
    mock_config_provider.get_config.return_value.STORAGE_EMULATOR_HOST = None
    gcs_provider = GcsProvider()
    mock_client = MagicMock()
    mock_client.bucket.side_effect = Exception("GCS Error")
    gcs_provider._client = mock_client

    # Act & Assert
    with pytest.raises(Exception, match="GCS Error"):
        gcs_provider.upload_file("test-bucket", "file.pdf", b"content", "application/pdf")
