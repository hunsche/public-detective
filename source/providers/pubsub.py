import os
import threading
from typing import cast

from google.cloud import pubsub_v1
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider


class PubSubProvider:
    """
    Provides a static method to publish messages directly to a Pub/Sub topic,
    handling client creation and caching internally.
    """

    logger: Logger = LoggingProvider().get_logger()
    config: Config = ConfigProvider.get_config()
    _publisher_client: pubsub_v1.PublisherClient | None = None
    _lock = threading.Lock()

    @staticmethod
    def _get_client() -> pubsub_v1.PublisherClient:
        """
        Internal method to safely create and return a singleton PublisherClient.
        This ensures the client is only instantiated once.
        """
        if PubSubProvider._publisher_client is not None:
            return PubSubProvider._publisher_client

        with PubSubProvider._lock:
            if PubSubProvider._publisher_client is None:
                PubSubProvider.logger.info(
                    "PublisherClient not found, creating a new one..."
                )
                emulator_host = PubSubProvider.config.GCP_PUBSUB_HOST

                if emulator_host:
                    os.environ["PUBSUB_EMULATOR_HOST"] = emulator_host
                    client = pubsub_v1.PublisherClient()
                    PubSubProvider.logger.info(
                        f"Client created for emulator at {emulator_host}"
                    )
                else:
                    client = pubsub_v1.PublisherClient()
                    PubSubProvider.logger.info("Client created for Google Cloud")

                PubSubProvider._publisher_client = client

        return PubSubProvider._publisher_client

    @staticmethod
    def publish(topic_id: str, data: bytes, timeout_seconds: int = 15) -> str:
        """
        Publishes a message to a specific topic.

        This static method handles getting the client, building the topic path,
        and publishing the message in a single call.

        :param topic_id: The ID of the Pub/Sub topic.
        :param data: The message payload as bytes.
        :param timeout_seconds: Max seconds to wait for publish confirmation.
        :return: The message ID of the published message.
        """
        try:
            client = PubSubProvider._get_client()

            topic_path = client.topic_path(PubSubProvider.config.GCP_PROJECT_ID, topic_id)

            future = client.publish(topic_path, b"teste")
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
