from unittest.mock import MagicMock, patch

import pytest
from google.cloud import pubsub_v1
from providers.pubsub import PubSubProvider


@pytest.fixture
def mock_config_provider():
    with patch("providers.config.ConfigProvider.get_config") as mock_get_config:
        yield mock_get_config


@pytest.fixture
def mock_logger_provider():
    with patch("providers.logging.LoggingProvider") as mock_logging_provider:
        yield mock_logging_provider


def test_create_client_instance_no_emulator(mock_config_provider, mock_logger_provider):
    """Tests that the client is created without emulator settings if the env var is not set."""
    with patch("os.environ.get", return_value=None):
        with patch("google.cloud.pubsub_v1.PublisherClient") as mock_publisher:
            mock_publisher.__name__ = "PublisherClient"
            provider = PubSubProvider()
            provider._create_client_instance(mock_publisher)
            mock_publisher.assert_called_once_with()


def test_get_or_create_publisher_client_caches_instance(mock_config_provider, mock_logger_provider):
    """Tests that the publisher client is created only once and then cached."""
    with patch("os.environ.get", return_value=None):
        with patch("google.cloud.pubsub_v1.PublisherClient") as mock_publisher:
            mock_publisher.__name__ = "PublisherClient"
            provider = PubSubProvider()
            # Call twice
            client1 = provider._get_or_create_publisher_client()
            client2 = provider._get_or_create_publisher_client()
            # Assert it was created only once
            mock_publisher.assert_called_once()
            assert client1 is client2
