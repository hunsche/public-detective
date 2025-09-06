from unittest.mock import MagicMock, patch

import pytest
from google.auth.credentials import AnonymousCredentials
from providers.gcs import GcsProvider


def test_gcs_provider_initialization(mocker) -> None:
    """
    Should initialize the GcsProvider with a logger, config, and lock.
    """
    # Arrange
    mock_logger = MagicMock()
    mock_config = MagicMock()
    mock_lock = MagicMock()

    mocker.patch("providers.gcs.LoggingProvider.get_logger", return_value=mock_logger)
    mocker.patch("providers.gcs.ConfigProvider.get_config", return_value=mock_config)
    mocker.patch("threading.Lock", return_value=mock_lock)

    # Act
    gcs_provider = GcsProvider()

    # Assert
    assert gcs_provider.logger is mock_logger
    assert gcs_provider.config is mock_config
    assert gcs_provider._client_creation_lock is mock_lock


def test_get_or_create_client_with_emulator(mocker) -> None:
    """
    Should create a GCS client with AnonymousCredentials when GCP_GCS_HOST is set.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config.GCP_GCS_HOST = "http://localhost:8086"
    mock_config.GCP_PROJECT = "test-project"
    mocker.patch("providers.gcs.ConfigProvider.get_config", return_value=mock_config)
    mocker.patch("providers.gcs.LoggingProvider.get_logger", return_value=MagicMock())

    gcs_provider = GcsProvider()
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


def test_get_or_create_client_for_production(mocker) -> None:
    """
    Should create a GCS client with default credentials when GCP_GCS_HOST is not set.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config.GCP_GCS_HOST = None  # Emulator is not set
    mock_config.GCP_PROJECT = "prod-project"
    mocker.patch("providers.gcs.ConfigProvider.get_config", return_value=mock_config)
    mocker.patch("providers.gcs.LoggingProvider.get_logger", return_value=MagicMock())

    gcs_provider = GcsProvider()
    gcs_provider._client = None  # Ensure client is recreated

    with patch("google.cloud.storage.Client") as mock_storage_client:
        # Act
        client = gcs_provider._get_or_create_client()

        # Assert
        mock_storage_client.assert_called_once_with(project="prod-project")
        assert client is not None


def test_get_or_create_client_caches_instance(mocker) -> None:
    """
    Should create a GCS client only once and then cache it.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config.GCP_GCS_HOST = None
    mock_config.GCP_PROJECT = "prod-project"
    mocker.patch("providers.gcs.ConfigProvider.get_config", return_value=mock_config)
    mocker.patch("providers.gcs.LoggingProvider.get_logger", return_value=MagicMock())

    gcs_provider = GcsProvider()
    gcs_provider._client = None

    with patch("google.cloud.storage.Client") as mock_storage_client:
        # Act
        client1 = gcs_provider._get_or_create_client()
        client2 = gcs_provider._get_or_create_client()

        # Assert
        mock_storage_client.assert_called_once()
        assert client1 is client2


def test_upload_file_success(mocker) -> None:
    """
    Should upload a file successfully and return its public URL.
    """
    # Arrange
    mocker.patch("providers.gcs.ConfigProvider.get_config", return_value=MagicMock())
    mocker.patch("providers.gcs.LoggingProvider.get_logger", return_value=MagicMock())
    gcs_provider = GcsProvider()
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.public_url = "http://fake-url/file.pdf"

    gcs_provider._get_or_create_client = MagicMock(return_value=mock_client)
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    # Act
    public_url = gcs_provider.upload_file("test-bucket", "file.pdf", b"content", "application/pdf")

    # Assert
    mock_client.bucket.assert_called_once_with("test-bucket")
    mock_bucket.blob.assert_called_once_with("file.pdf")
    mock_blob.upload_from_string.assert_called_once_with(b"content", content_type="application/pdf")
    assert public_url == "http://fake-url/file.pdf"


def test_upload_file_failure(mocker) -> None:
    """
    Should raise an exception when the upload fails.
    """
    # Arrange
    mocker.patch("providers.gcs.ConfigProvider.get_config", return_value=MagicMock())
    mocker.patch("providers.gcs.LoggingProvider.get_logger", return_value=MagicMock())
    gcs_provider = GcsProvider()
    mock_client = MagicMock()
    mock_client.bucket.side_effect = Exception("GCS Error")
    gcs_provider._get_or_create_client = MagicMock(return_value=mock_client)

    # Act & Assert
    with pytest.raises(Exception, match="GCS Error"):
        gcs_provider.upload_file("test-bucket", "file.pdf", b"content", "application/pdf")


def test_download_file_success(mocker) -> None:
    """
    Should download a file successfully and return its content.
    """
    # Arrange
    mocker.patch("providers.gcs.ConfigProvider.get_config", return_value=MagicMock())
    mocker.patch("providers.gcs.LoggingProvider.get_logger", return_value=MagicMock())
    gcs_provider = GcsProvider()
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.download_as_bytes.return_value = b"file content"

    gcs_provider._get_or_create_client = MagicMock(return_value=mock_client)
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    # Act
    content = gcs_provider.download_file("test-bucket", "file.pdf")

    # Assert
    mock_client.bucket.assert_called_once_with("test-bucket")
    mock_bucket.blob.assert_called_once_with("file.pdf")
    mock_blob.download_as_bytes.assert_called_once()
    assert content == b"file content"


def test_download_file_empty(mocker) -> None:
    """
    Should return None when the downloaded file is empty.
    """
    # Arrange
    mocker.patch("providers.gcs.ConfigProvider.get_config", return_value=MagicMock())
    mocker.patch("providers.gcs.LoggingProvider.get_logger", return_value=MagicMock())
    gcs_provider = GcsProvider()
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.download_as_bytes.return_value = b""

    gcs_provider._get_or_create_client = MagicMock(return_value=mock_client)
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    # Act
    content = gcs_provider.download_file("test-bucket", "file.pdf")

    # Assert
    assert content is None
    gcs_provider.logger.warning.assert_called_once()


def test_download_file_failure(mocker) -> None:
    """
    Should raise an exception when the download fails.
    """
    # Arrange
    mocker.patch("providers.gcs.ConfigProvider.get_config", return_value=MagicMock())
    mocker.patch("providers.gcs.LoggingProvider.get_logger", return_value=MagicMock())
    gcs_provider = GcsProvider()
    mock_client = MagicMock()
    mock_client.bucket.side_effect = Exception("GCS Error")
    gcs_provider._get_or_create_client = MagicMock(return_value=mock_client)

    # Act & Assert
    with pytest.raises(Exception, match="GCS Error"):
        gcs_provider.download_file("test-bucket", "file.pdf")
