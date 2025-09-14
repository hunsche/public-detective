import os
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.client_options import ClientOptions
from google.cloud.pubsub_v1 import PublisherClient, SubscriberClient
from public_detective.providers.pubsub import PubSubProvider


@pytest.fixture
def mock_config_provider() -> Generator[MagicMock, None, None]:
    with patch("public_detective.providers.config.ConfigProvider.get_config") as mock_get_config:
        mock_get_config.return_value.GCP_PROJECT = "test-project"
        yield mock_get_config


@pytest.fixture
def pubsub_provider(mock_config_provider: MagicMock) -> PubSubProvider:
    return PubSubProvider()


def test_create_client_instance_no_emulator(pubsub_provider: PubSubProvider) -> None:
    """Tests that the client is created without emulator settings if the env var is not set.

    Args:
        pubsub_provider: The PubSubProvider instance.
    """
    with patch.dict(os.environ, {}, clear=True):
        with patch("google.cloud.pubsub_v1.PublisherClient") as mock_publisher:
            mock_publisher.__name__ = "PublisherClient"
            pubsub_provider._create_client_instance(mock_publisher)
            mock_publisher.assert_called_once_with()


def test_create_client_instance_with_emulator(pubsub_provider: PubSubProvider) -> None:
    """Tests that the client is created with emulator settings if the env var is set.

    Args:
        pubsub_provider: The PubSubProvider instance.
    """
    emulator_host = "localhost:8085"
    with patch.dict(os.environ, {"PUBSUB_EMULATOR_HOST": emulator_host}, clear=True):
        with patch("google.cloud.pubsub_v1.PublisherClient") as mock_publisher:
            mock_publisher.__name__ = "PublisherClient"
            pubsub_provider._create_client_instance(mock_publisher)
            mock_publisher.assert_called_once()
            # Check that ClientOptions was called with the correct endpoint
            args, kwargs = mock_publisher.call_args
            assert "client_options" in kwargs
            assert isinstance(kwargs["client_options"], ClientOptions)
            assert kwargs["client_options"].api_endpoint == emulator_host


def test_get_or_create_publisher_client_caches_instance(pubsub_provider: PubSubProvider) -> None:
    """Tests that the publisher client is created only once and then cached.

    Args:
        pubsub_provider: The PubSubProvider instance.
    """
    with patch.object(pubsub_provider, "_create_client_instance") as mock_create:
        client1 = pubsub_provider._get_or_create_publisher_client()
        client2 = pubsub_provider._get_or_create_publisher_client()
        mock_create.assert_called_once_with(PublisherClient)
        assert client1 is client2


def test_get_or_create_subscriber_client_caches_instance(pubsub_provider: PubSubProvider) -> None:
    """Tests that the subscriber client is created only once and then cached.

    Args:
        pubsub_provider: The PubSubProvider instance.
    """
    with patch.object(pubsub_provider, "_create_client_instance") as mock_create:
        client1 = pubsub_provider._get_or_create_subscriber_client()
        client2 = pubsub_provider._get_or_create_subscriber_client()
        mock_create.assert_called_once_with(SubscriberClient)
        assert client1 is client2


@patch.object(PubSubProvider, "_get_or_create_publisher_client")
def test_publish_success(mock_get_publisher: MagicMock, pubsub_provider: PubSubProvider) -> None:
    mock_publisher_instance = MagicMock()
    future = MagicMock()
    future.result.return_value = "message-id"
    mock_publisher_instance.publish.return_value = future
    mock_get_publisher.return_value = mock_publisher_instance

    message_id = pubsub_provider.publish("test-topic", b"test-data")

    assert message_id == "message-id"
    mock_publisher_instance.topic_path.assert_called_once_with("test-project", "test-topic")
    mock_publisher_instance.publish.assert_called_once()


@patch.object(PubSubProvider, "_get_or_create_publisher_client")
def test_publish_timeout(mock_get_publisher: MagicMock, pubsub_provider: PubSubProvider) -> None:
    mock_publisher_instance = MagicMock()
    future = MagicMock()
    future.result.side_effect = TimeoutError
    mock_publisher_instance.publish.return_value = future
    mock_get_publisher.return_value = mock_publisher_instance

    with pytest.raises(TimeoutError):
        pubsub_provider.publish("test-topic", b"test-data")


@patch.object(PubSubProvider, "_get_or_create_publisher_client")
def test_publish_exception(mock_get_publisher: MagicMock, pubsub_provider: PubSubProvider) -> None:
    mock_publisher_instance = MagicMock()
    mock_publisher_instance.publish.side_effect = Exception("Pub/Sub error")
    mock_get_publisher.return_value = mock_publisher_instance

    with pytest.raises(Exception, match="Pub/Sub error"):
        pubsub_provider.publish("test-topic", b"test-data")


@patch.object(PubSubProvider, "_get_or_create_subscriber_client")
def test_subscribe_success(mock_get_subscriber: MagicMock, pubsub_provider: PubSubProvider) -> None:
    mock_subscriber_instance = MagicMock()
    mock_streaming_pull_future = MagicMock()
    mock_subscriber_instance.subscribe.return_value = mock_streaming_pull_future
    mock_get_subscriber.return_value = mock_subscriber_instance

    def callback(message: MagicMock) -> None:
        pass

    future = pubsub_provider.subscribe("test-subscription", callback)

    assert future is mock_streaming_pull_future
    mock_subscriber_instance.subscription_path.assert_called_once_with("test-project", "test-subscription")
    mock_subscriber_instance.subscribe.assert_called_once()


@patch.object(PubSubProvider, "_get_or_create_subscriber_client")
def test_subscribe_exception(mock_get_subscriber: MagicMock, pubsub_provider: PubSubProvider) -> None:
    mock_subscriber_instance = MagicMock()
    mock_subscriber_instance.subscribe.side_effect = Exception("Sub error")
    mock_get_subscriber.return_value = mock_subscriber_instance

    def callback(message: MagicMock) -> None:
        pass

    with pytest.raises(Exception, match="Sub error"):
        pubsub_provider.subscribe("test-subscription", callback)
