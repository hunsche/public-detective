import json
import threading
from contextlib import contextmanager

from google.api_core.exceptions import GoogleAPICallError
from google.cloud.pubsub_v1.subscriber.futures import StreamingPullFuture
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

    _lock: threading.Lock | None = None
    config: Config
    logger: Logger
    analysis_service: AnalysisService
    processed_messages_count: int
    streaming_pull_future: StreamingPullFuture | None

    def __init__(self):
        """Initializes the worker, loading configuration and services."""
        self.config = ConfigProvider.get_config()
        self.logger = LoggingProvider().get_logger()
        self.analysis_service = AnalysisService()
        self.pubsub_provider = PubSubProvider()
        self.processed_messages_count = 0
        self.streaming_pull_future = None
        self._stop_event = threading.Event()

        if self.config.IS_DEBUG_MODE:
            self._lock = threading.Lock()

    @contextmanager
    def _debug_context(self, message: Message):
        """Serializes processing and extends ack deadline when in debug mode.

        Args:
            message: The Pub/Sub message currently being processed.

        Yields:
            A context that guarantees single-message processing in debug mode.
        """
        assert self._lock is not None
        with self._lock:
            self._extend_ack_deadline(message, 600)
            yield

    def _extend_ack_deadline(self, message: Message, seconds: int):
        """Attempts to extend the message ack deadline for safer debugging.

        Args:
            message: The Pub/Sub message to modify.
            seconds: Number of seconds to extend the ack deadline.
        """
        try:
            message.modify_ack_deadline(seconds)
            self.logger.debug(f"Ack deadline extended by {seconds}s.")
        except Exception:
            self.logger.debug("Unable to extend ack deadline; continuing.")

    def _debug_pause(self, prompt: str = ">> Press Enter to process...\n") -> None:
        """Pauses execution in debug mode to allow step-by-step inspection.

        Args:
            prompt: Prompt displayed while waiting for user input.
        """
        try:
            input(prompt)
        except EOFError:
            self.logger.debug("No TTY available; skipping pause.")

    def _process_message(self, message: Message):
        """Decodes, validates, analyzes the message, and manages ACK/NACK.

        Args:
            message: The Pub/Sub message to process.
        """
        message_id = message.message_id
        self.logger.info(f"Received message ID: {message_id}. Attempting to process...")

        try:
            data_str = message.data.decode()
            procurement = Procurement.model_validate_json(data_str)
            self.logger.info(f"Validated message for procurement {procurement.pncp_control_number}.")

            if self.config.IS_DEBUG_MODE:
                self._debug_pause()

            self.analysis_service.analyze_procurement(procurement)

            self.logger.info(f"Message {message_id} processed successfully. Sending ACK.")
            message.ack()

        except (json.JSONDecodeError, ValidationError):
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

    def _message_callback(self, message: Message, max_messages: int | None):
        """Entry-point callback invoked by Pub/Sub upon message delivery.

        Applies a debug-only context (single-flight + extended deadline) and
        delegates to the core processing function.

        Args:
            message: The Pub/Sub message received from the subscription.
            max_messages: The maximum number of messages to process.
        """
        if self._stop_event.is_set():
            return

        if self.config.IS_DEBUG_MODE:
            ctx = self._debug_context(message)
            with ctx:
                self._process_message(message)
        else:
            self._process_message(message)

        self.processed_messages_count += 1
        if max_messages and self.processed_messages_count >= max_messages:
            self.logger.info(f"Reached message limit ({max_messages}). Stopping worker...")
            self._stop_event.set()
            if self.streaming_pull_future:
                self.streaming_pull_future.cancel()

    def run(self, max_messages: int | None = None):
        """Starts the worker's message consumption loop.

        This method initiates the subscription to the configured Pub/Sub topic
        and blocks indefinitely, waiting for messages. It includes logic for
        graceful shutdown upon interruption.
        """
        subscription_name = self.config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS
        if not subscription_name:
            self.logger.critical("Subscription name not configured. Worker cannot start.")
            return

        def callback(message: Message):
            self._message_callback(message, max_messages)

        self.streaming_pull_future = self.pubsub_provider.subscribe(subscription_name, callback)
        self.logger.info("Worker is now running and waiting for messages...")

        try:
            self.streaming_pull_future.result(timeout=None)
        except (TimeoutError, GoogleAPICallError, KeyboardInterrupt) as e:
            self.logger.warning(f"Shutdown requested: {type(e).__name__}")
        except Exception as e:
            if "cancelled" not in str(e).lower():
                self.logger.critical(f"A critical error stopped the worker: {e}", exc_info=True)
        finally:
            self.logger.info("Stopping worker...")
            if self.streaming_pull_future and not self.streaming_pull_future.cancelled():
                self.streaming_pull_future.cancel()
                self.streaming_pull_future.result()  # Wait for cancellation to complete
            self.logger.info("Worker has stopped gracefully.")
