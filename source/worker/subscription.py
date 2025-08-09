import json

from google.api_core.exceptions import GoogleAPICallError
from models.procurement import Procurement
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider
from providers.pubsub import Message, PubSubProvider
from pydantic import ValidationError
from services.analysis import AnalysisService


class Subscription:
    """Encapsulates a Google Cloud Pub/Sub worker that consumes, validates,
    and processes procurement messages.

    Its primary role is to act as the entry point for asynchronous processing,
    delegating the core business logic to the AnalysisService and ensuring
    robust message lifecycle management.
    """

    config: Config
    logger: Logger
    analysis_service: AnalysisService

    def __init__(self) -> None:
        """Initializes the worker, loading configuration and services."""
        self.config = ConfigProvider.get_config()
        self.logger = LoggingProvider().get_logger()
        self.analysis_service = AnalysisService()

    def _message_callback(self, message: Message) -> None:
        """Handles an incoming message from the Pub/Sub subscription.

        This callback decodes, validates, and passes the message to the
        analysis service. It manages the message's ack/nack lifecycle to ensure
        that messages are re-processed in case of transient failures and sent
        to a dead-letter queue for persistent errors.

        Args:
            message: The message object received from Pub/Sub.
        """
        message_id = message.message_id
        self.logger.info(f"Received message ID: {message_id}. Attempting to process...")

        try:
            data_str = message.data.decode()
            procurement = Procurement.model_validate_json(data_str)
            self.logger.info(
                f"Validated message for procurement {procurement.pncp_control_number}."
            )

            self.analysis_service.analyze_procurement(procurement)

            self.logger.info(f"Message {message_id} processed successfully. Sending ACK.")
            message.ack()

        except (json.JSONDecodeError, ValidationError) as e:
            self.logger.error(
                f"Validation/decoding failed for message {message_id}. Sending NACK.",
                exc_info=True,
            )
            message.nack()
        except Exception as e:
            self.logger.error(
                f"Unexpected error processing message {message_id}: {e}",
                exc_info=True,
            )
            message.nack()

    def run(self) -> None:
        """Starts the worker's message consumption loop.

        This method initiates the subscription to the configured Pub/Sub topic
        and blocks indefinitely, waiting for messages. It includes logic for
        graceful shutdown upon interruption.
        """
        subscription_name = self.config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS
        if not subscription_name:
            self.logger.critical("Subscription name not configured. Worker cannot start.")
            return

        streaming_pull_future = PubSubProvider.subscribe(
            subscription_name, self._message_callback
        )
        self.logger.info("Worker is now running and waiting for messages...")

        try:
            streaming_pull_future.result(
                # timeout=None
            )  # TO DO: Remove timeout=None to allow graceful shutdown
        except (TimeoutError, GoogleAPICallError, KeyboardInterrupt) as e:
            self.logger.warning(f"Shutdown requested: {type(e).__name__}")
        except Exception as e:
            self.logger.critical(
                f"A critical error stopped the worker: {e}", exc_info=True
            )
        finally:
            self.logger.info("Stopping worker...")
            streaming_pull_future.cancel()
            streaming_pull_future.result()
            self.logger.info("Worker has stopped gracefully.")
