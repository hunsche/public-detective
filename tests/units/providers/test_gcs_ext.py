from unittest.mock import MagicMock, patch

import pytest
from public_detective.providers.gcs import GcsProvider


@patch("public_detective.providers.gcs.ConfigProvider")
@patch("public_detective.providers.gcs.Client")
def test_get_client_real_credentials(mock_gcs_client, mock_config_provider):
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