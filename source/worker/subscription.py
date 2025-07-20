import json

from google.api_core.exceptions import GoogleAPICallError
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider
from providers.pubsub import Message, PubSubProvider
from pydantic import ValidationError


class Subscription:
    """
    A class to encapsulate a Google Cloud Pub/Sub worker.

    This worker connects to a specified subscription, listens for messages,
    validates them using a Pydantic model, processes them, and handles
    acknowledgements (ack/nack) for robust message processing.
    """

    config: Config
    logger: Logger

    def __init__(self):
        """
        Initializes the WorkerSubscription.

        Loads configuration from environment variables, creates a Pub/Sub
        subscriber client, and builds the full subscription path.
        """
        self.config = ConfigProvider().get_config()
        self.logger = LoggingProvider().get_logger()

    def _message_callback(self, message: Message) -> None:
        """
        Handles incoming messages from the Pub/Sub subscription.

        This callback function is executed for each message received. It
        manages the full lifecycle of a message: decoding, validation,
        processing, and final acknowledgement (ack) or negative
        acknowledgement (nack).

        Args:
            message: The message object received from Pub/Sub.
        """
        message_id = message.message_id
        self.logger.info(f"Received message ID: {message_id}. Attempting to process...")

        try:
            data_str = message.data.decode()
            self.logger.info(f"Raw data: {data_str}")

            self.logger.info(f"Message {message_id} processed successfully. Sending ACK.")
            message.ack()

        except json.JSONDecodeError:
            self.logger.error(
                f"Failed to decode JSON for message {message_id}. Sending NACK."
            )
            message.nack()

        except ValidationError as e:
            self.logger.error(
                f"Pydantic validation failed for message {message_id}. Sending NACK."
            )
            self.logger.error(e)
            message.nack()

        except Exception as e:
            self.logger.error(
                f"An unexpected error occurred while processing message {message_id}: {e}",
                exc_info=True,
            )
            message.nack()

    def run(self) -> None:
        """
        Starts the worker's message consumption loop.

        This method initiates the subscription to the Pub/Sub topic and blocks
        indefinitely, waiting for messages. It handles graceful shutdown
        on KeyboardInterrupt (Ctrl+C).
        """
        streaming_pull_future = PubSubProvider.subscribe(
            self.config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS, self._message_callback
        )

        try:
            streaming_pull_future.result()
        except (TimeoutError, GoogleAPICallError, KeyboardInterrupt) as e:
            self.logger.error(f"Worker shutdown due to: {e}")
            streaming_pull_future.cancel()
            streaming_pull_future.result()
            self.logger.info("Worker has been stopped gracefully.")
        except Exception as e:
            self.logger.error(f"A critical error stopped the worker: {e}", exc_info=True)
            streaming_pull_future.cancel()
