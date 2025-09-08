"""This module provides a thread-safe provider for Google Cloud Pub/Sub.

It defines a `PubSubProvider` class that abstracts the interaction with
Pub/Sub, including thread-safe, cached client management for both publishing
and subscribing. It supports emulator usage for local development and testing.
"""

import os
import threading
from collections.abc import Callable
from typing import cast

from google.api_core.client_options import ClientOptions
from google.cloud.pubsub_v1 import PublisherClient, SubscriberClient
from google.cloud.pubsub_v1.publisher.futures import Future
from google.cloud.pubsub_v1.subscriber.futures import StreamingPullFuture
from google.cloud.pubsub_v1.subscriber.message import Message
from google.cloud.pubsub_v1.types import FlowControl
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider


class PubSubProvider:
    """Provides methods to interact with Google Cloud Pub/Sub.

    This provider centralizes client management, abstracting away the
    instantiation and caching of both Publisher and Subscriber clients in a
    thread-safe manner, offering a simple and elegant interface for
    publishing and subscribing to topics.
    """

    _clients: dict[str, SubscriberClient | PublisherClient]
    _client_creation_lock: threading.Lock
    logger: Logger
    config: Config

    def __init__(self) -> None:
        """Initializes the PubSubProvider.

        This constructor sets up the logger, loads the application
        configuration, and initializes a thread-safe lock and a dictionary
        to cache client instances.
        """
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()
        self._clients = {}
        self._client_creation_lock = threading.Lock()

    def _create_client_instance(
        self,
        client_class: type[SubscriberClient | PublisherClient],
    ) -> SubscriberClient | PublisherClient:
        """Internal helper to create a new GCP client instance.

        This method handles emulator setup.
        This method centralizes the logic for instantiating a Pub/Sub client
        and configuring it for either the emulator or the actual Google Cloud
        environment.

        Args:
            client_class: The class of the GCP client to instantiate (e.g.,
                          pubsub_v1.PublisherClient,
                          pubsub_v1.SubscriberClient).

        Returns:
            An instance of the specified GCP client class.
        """
        class_name = client_class.__name__
        self.logger.info(f"{class_name} not found in cache, creating a new instance...")
        emulator_host = os.environ.get("PUBSUB_EMULATOR_HOST")

        if emulator_host:
            client_options = ClientOptions(api_endpoint=emulator_host)
            client = client_class(client_options=client_options)
            self.logger.info(f"{class_name} instance created for emulator at {emulator_host}")
        else:
            client = client_class()
            self.logger.info(f"{class_name} instance created for Google Cloud")
        return client

    def _get_or_create_publisher_client(self) -> PublisherClient:
        """Retrieves a singleton instance of the Pub/Sub PublisherClient.

        If a PublisherClient instance does not exist in the cache, it creates
        a new one in a thread-safe manner, caches it, and then returns it.

        Returns:
            A singleton instance of google.cloud.pubsub_v1.PublisherClient.
        """
        client_key = PublisherClient.__name__

        if client_key not in self._clients:
            with self._client_creation_lock:
                if client_key not in self._clients:
                    client = self._create_client_instance(PublisherClient)
                    self._clients[client_key] = client
        return cast(PublisherClient, self._clients[client_key])

    def _get_or_create_subscriber_client(self) -> SubscriberClient:
        """Retrieves a singleton instance of the Pub/Sub SubscriberClient.

        If a SubscriberClient instance does not exist in the cache, it creates
        a new one in a thread-safe manner, caches it, and then returns it.

        Returns:
            A singleton instance of google.cloud.pubsub_v1.SubscriberClient.
        """
        client_key = SubscriberClient.__name__

        if client_key not in self._clients:
            with self._client_creation_lock:
                if client_key not in self._clients:
                    client = self._create_client_instance(SubscriberClient)
                    self._clients[client_key] = client
        return cast(SubscriberClient, self._clients[client_key])

    def publish(self, topic_id: str, data: bytes, timeout_seconds: int = 15) -> str:
        """Publishes a message to a specific Pub/Sub topic.

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
        """
        try:
            client = self._get_or_create_publisher_client()
            topic_path = client.topic_path(self.config.GCP_PROJECT, topic_id)
            self.logger.info(f"Publishing to topic: {topic_path}")

            future = cast(Future, client.publish(topic_path, data))
            message_id = future.result(timeout=timeout_seconds)

            self.logger.debug(f"Message {message_id} published to {topic_path}")
            return cast(str, message_id)
        except TimeoutError:
            self.logger.error(f"Publishing to topic {topic_id} timed out after {timeout_seconds} seconds.")
            raise
        except Exception as e:
            self.logger.error(f"Failed to publish to topic {topic_id}: {e}")
            raise

    def subscribe(
        self,
        subscription_id: str,
        callback: Callable[[Message], None],
        flow_control: FlowControl | None = None,
    ) -> StreamingPullFuture:
        """Starts listening to a Pub/Sub subscription and executes a callback for each message.

        This method retrieves a cached SubscriberClient and initiates a
        streaming pull request to the specified subscription. The provided
        callback function will be invoked for each message received.

        The method returns a `StreamingPullFuture` object, which must be
        managed by the caller (e.g., by calling `future.result()` to block
        the main thread or `future.cancel()` to stop the subscription).

        Args:
            subscription_id: The ID of the Pub/Sub subscription to listen to.
            callback: The function to execute for each received message. It
                      should accept one argument: a
                      `google.cloud.pubsub_v1.subscriber.message.Message`
                      object.
            flow_control: An optional `FlowControl` object to configure
                          concurrency and rate limiting.

        Returns:
            A `google.cloud.pubsub_v1.subscriber.futures.StreamingPullFuture`
            instance to manage the subscription lifecycle.

        Raises:
            Exception: For any errors encountered while attempting to start
                       the subscription.
        """
        try:
            client = self._get_or_create_subscriber_client()
            subscription_path = client.subscription_path(self.config.GCP_PROJECT, subscription_id)
            self.logger.info(f"Subscribing to subscription: {subscription_path}")

            streaming_pull_future = client.subscribe(subscription_path, callback=callback, flow_control=flow_control)

            self.logger.info(f"Successfully subscribed to {subscription_path}. Waiting for messages...")
            return streaming_pull_future
        except Exception as e:
            self.logger.error(f"Failed to start subscription on {subscription_id}: {e}")
            raise
