import os
import threading
from collections.abc import Callable
from typing import cast

from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.publisher.futures import Future
from google.cloud.pubsub_v1.subscriber.futures import StreamingPullFuture
from google.cloud.pubsub_v1.subscriber.message import Message
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider


class PubSubProvider:
    """
    Provides static methods to interact with Google Cloud Pub/Sub.

    This provider centralizes client management, abstracting away the
    instantiation and caching of both Publisher and Subscriber clients in a
    thread-safe manner, offering a simple and elegant interface for
    publishing and subscribing to topics.
    """

    logger: Logger = LoggingProvider().get_logger()
    config: Config = ConfigProvider.get_config()

    _clients: dict[str, pubsub_v1.SubscriberClient | pubsub_v1.PublisherClient] = {}
    _client_creation_lock = threading.Lock()

    @staticmethod
    def _create_client_instance(
        client_class: type[pubsub_v1.SubscriberClient | pubsub_v1.PublisherClient],
    ) -> pubsub_v1.SubscriberClient | pubsub_v1.PublisherClient:
        """
        Internal helper to create a new GCP client instance, handling emulator setup.

        This method centralizes the logic for instantiating a Pub/Sub client
        and configuring it for either the emulator or the actual Google Cloud
        environment.

        Args:
            client_class: The class of the GCP client to instantiate (e.g.,
                          pubsub_v1.PublisherClient, pubsub_v1.SubscriberClient).

        Returns:
            An instance of the specified GCP client class.
        """
        class_name = client_class.__name__
        PubSubProvider.logger.info(
            f"{class_name} not found in cache, creating a new instance..."
        )
        emulator_host = PubSubProvider.config.GCP_PUBSUB_HOST

        if emulator_host:
            os.environ["PUBSUB_EMULATOR_HOST"] = emulator_host
            client = client_class()
            PubSubProvider.logger.info(
                f"{class_name} instance created for emulator at {emulator_host}"
            )
        else:
            client = client_class()
            PubSubProvider.logger.info(f"{class_name} instance created for Google Cloud")
        return client

    @staticmethod
    def _get_or_create_publisher_client() -> pubsub_v1.PublisherClient:
        """
        Retrieves a singleton instance of the Pub/Sub PublisherClient.

        If a PublisherClient instance does not exist in the cache, it creates
        a new one in a thread-safe manner, caches it, and then returns it.

        Returns:
            A singleton instance of google.cloud.pubsub_v1.PublisherClient.
        """
        client_key = pubsub_v1.PublisherClient.__name__

        if client_key not in PubSubProvider._clients:
            with PubSubProvider._client_creation_lock:
                if client_key not in PubSubProvider._clients:
                    PubSubProvider._clients[client_key] = (
                        PubSubProvider._create_client_instance(pubsub_v1.PublisherClient)
                    )
        return cast(pubsub_v1.PublisherClient, PubSubProvider._clients[client_key])

    @staticmethod
    def _get_or_create_subscriber_client() -> pubsub_v1.SubscriberClient:
        """
        Retrieves a singleton instance of the Pub/Sub SubscriberClient.

        If a SubscriberClient instance does not exist in the cache, it creates
        a new one in a thread-safe manner, caches it, and then returns it.

        Returns:
            A singleton instance of google.cloud.pubsub_v1.SubscriberClient.
        """
        client_key = pubsub_v1.SubscriberClient.__name__

        if client_key not in PubSubProvider._clients:
            with PubSubProvider._client_creation_lock:
                if client_key not in PubSubProvider._clients:
                    PubSubProvider._clients[client_key] = (
                        PubSubProvider._create_client_instance(pubsub_v1.SubscriberClient)
                    )
        return cast(pubsub_v1.SubscriberClient, PubSubProvider._clients[client_key])

    @staticmethod
    def publish(topic_id: str, data: bytes, timeout_seconds: int = 15) -> str:
        """
        Publishes a message to a specific Pub/Sub topic.

        This method retrieves a cached PublisherClient, constructs the topic path,
        publishes the message, and waits for a confirmation within a specified
        timeout.

        Args:
            topic_id: The ID of the Pub/Sub topic to publish to.
            data: The message payload as bytes.
            timeout_seconds: The maximum number of seconds to wait for
                             publish confirmation. Defaults to 15 seconds.

        Returns:
            The message ID of the published message.

        Raises:
            TimeoutError: If publishing times out.
            Exception: For any other errors during the publish operation.
        """
        try:
            client = PubSubProvider._get_or_create_publisher_client()
            topic_path = client.topic_path(PubSubProvider.config.GCP_PROJECT, topic_id)

            future = cast(Future, client.publish(topic_path, data))
            message_id = future.result(timeout=timeout_seconds)

            PubSubProvider.logger.debug(f"Message {message_id} published to {topic_path}")
            return cast(str, message_id)
        except TimeoutError:
            PubSubProvider.logger.error(
                f"Publishing to topic {topic_id} timed out after {timeout_seconds} seconds."
            )
            raise
        except Exception as e:
            PubSubProvider.logger.error(f"Failed to publish to topic {topic_id}: {e}")
            raise

    @staticmethod
    def subscribe(
        subscription_id: str, callback: Callable[[Message], None]
    ) -> StreamingPullFuture:
        """
        Starts listening to a Pub/Sub subscription and executes a callback for each message.

        This method retrieves a cached SubscriberClient and initiates a streaming
        pull request to the specified subscription. The provided callback function
        will be invoked for each message received.

        The method returns a `StreamingPullFuture` object, which must be managed
        by the caller (e.g., by calling `future.result()` to block the main
        thread or `future.cancel()` to stop the subscription).

        Args:
            subscription_id: The ID of the Pub/Sub subscription to listen to.
            callback: The function to execute for each received message.
                      It should accept one argument: a `google.cloud.pubsub_v1.subscriber.message.Message` object.

        Returns:
            A `google.cloud.pubsub_v1.subscriber.futures.StreamingPullFuture`
            instance to manage the subscription lifecycle.

        Raises:
            Exception: For any errors encountered while attempting to start
                       the subscription.
        """
        try:
            client = PubSubProvider._get_or_create_subscriber_client()
            subscription_path = client.subscription_path(
                PubSubProvider.config.GCP_PROJECT, subscription_id
            )

            streaming_pull_future = client.subscribe(subscription_path, callback=callback)

            PubSubProvider.logger.info(
                f"Successfully subscribed to {subscription_path}. Waiting for messages..."
            )
            return streaming_pull_future
        except Exception as e:
            PubSubProvider.logger.error(
                f"Failed to start subscription on {subscription_id}: {e}"
            )
            raise
