import os
from unittest.mock import patch

from google.cloud import storage

from source.providers.gcs import GcsProvider


def test_gcs_client_creation_for_production():
    if "GCP_GCS_HOST" in os.environ:
        del os.environ["GCP_GCS_HOST"]

    with patch.object(storage, "Client") as mock_client:
        provider = GcsProvider()
        provider._get_or_create_client()
        mock_client.assert_called_with(project=provider.config.GCP_PROJECT)
