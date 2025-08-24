from unittest.mock import MagicMock, patch

import pytest
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
        mock_storage_client.assert_called_once()
        _, kwargs = mock_storage_client.call_args
        # When no credentials are provided, the client uses the default auth chain.
        assert "credentials" not in kwargs
        assert kwargs["project"] == "prod-project"
        assert client is not None
