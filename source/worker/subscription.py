"""This module defines the core Pub/Sub subscription worker.

It contains the `Subscription` class, which encapsulates the logic for
listening to a Pub/Sub topic, processing messages, and managing the
message lifecycle (ACK/NACK). The worker is designed to be robust,
handling JSON validation, graceful shutdowns, and providing hooks for
debugging.
"""

import json
import threading
import uuid
from contextlib import contextmanager

from google.api_core.exceptions import GoogleAPICallError
from google.cloud.pubsub_v1.subscriber.futures import StreamingPullFuture
from models.analyses import Analysis
from providers.ai import AiProvider
from providers.config import Config, ConfigProvider
from providers.database import DatabaseManager
from providers.gcs import GcsProvider
from providers.logging import Logger, LoggingProvider
from providers.pubsub import Message, PubSubProvider
from pydantic import ValidationError
from repositories.analyses import AnalysisRepository
from repositories.budget_ledger import BudgetLedgerRepository
from repositories.file_records import FileRecordsRepository
from repositories.procurements import ProcurementsRepository
from repositories.status_history import StatusHistoryRepository
from services.analysis import AnalysisService


class Subscription:
    """Encapsulates a Google Cloud Pub/Sub worker that consumes, validates,
    and processes procurement messages.

    Its primary role is to act as the entry point for asynchronous processing,
    delegating the core business logic to the AnalysisService and ensuring
    robust message lifecycle management.
    """

    _lock: threading.Lock
    config: Config
    logger: Logger
    analysis_service: AnalysisService
    procurement_repo: ProcurementsRepository
    processed_messages_count: int
    streaming_pull_future: StreamingPullFuture | None
    pubsub_provider: PubSubProvider
    _stop_event: threading.Event

    def __init__(self, analysis_service: AnalysisService | None = None):
        """Initializes the worker, loading configuration and services.

        This constructor acts as the Composition Root for the worker application.
        It instantiates and wires together all the necessary dependencies.
        """
        self.config = ConfigProvider.get_config()
        self.logger = LoggingProvider().get_logger()
        self.pubsub_provider = PubSubProvider()

        if analysis_service:
            self.analysis_service = analysis_service
            self.procurement_repo = self.analysis_service.procurement_repo
        else:
            db_engine = DatabaseManager.get_engine()
            gcs_provider = GcsProvider()
            ai_provider = AiProvider(Analysis)

            analysis_repo = AnalysisRepository(engine=db_engine)
            file_record_repo = FileRecordsRepository(engine=db_engine)
            self.procurement_repo = ProcurementsRepository(engine=db_engine, pubsub_provider=self.pubsub_provider)

            status_history_repo = StatusHistoryRepository(engine=db_engine)
            budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)
            self.analysis_service = AnalysisService(
                procurement_repo=self.procurement_repo,
                analysis_repo=analysis_repo,
                file_record_repo=file_record_repo,
                status_history_repo=status_history_repo,
                budget_ledger_repo=budget_ledger_repo,
                ai_provider=ai_provider,
                gcs_provider=gcs_provider,
            )

        self.processed_messages_count = 0
        self.streaming_pull_future = None
        self._stop_event = threading.Event()
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

    def _process_message(self, message: Message, max_output_tokens: int | None = None):
        """Decodes, validates, analyzes the message, and manages ACK/NACK."""
        message_id = message.message_id
        try:
            data_str = message.data.decode()
            message_data = json.loads(data_str)
            analysis_id = message_data["analysis_id"]

            analysis = self.analysis_service.analysis_repo.get_analysis_by_id(analysis_id)
            if not analysis:
                self.logger.error(f"Analysis with ID {analysis_id} not found in message {message_id}. Sending NACK.")
                message.nack()
                return

            procurement_id = analysis.procurement_control_number
            correlation_id = f"{procurement_id}:{analysis_id}:{uuid.uuid4().hex[:8]}"

            with LoggingProvider().set_correlation_id(correlation_id):
                self.logger.info(
                    f"Received message ID: {message_id} for procurement {procurement_id} "
                    f"(analysis_id: {analysis_id}). Attempting to process..."
                )

                self.analysis_service.process_analysis_from_message(analysis_id, max_output_tokens=max_output_tokens)

                self.logger.info(
                    f"Message {message_id} for procurement {procurement_id} processed successfully. Sending ACK."
                )
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

    def _message_callback(self, message: Message, max_messages: int | None, max_output_tokens: int | None = None):
        """Entry-point callback invoked by Pub/Sub upon message delivery.

        Applies a debug-only context (single-flight + extended deadline) and
        delegates to the core processing function.

        Args:
            message: The Pub/Sub message received from the subscription.
            max_messages: The maximum number of messages to process.
            max_output_tokens: The token limit to apply to the analysis.
        """
        with self._lock:
            if self._stop_event.is_set():
                return

            self._process_message(message, max_output_tokens)

            self.processed_messages_count += 1
            if max_messages and self.processed_messages_count >= max_messages:
                self.logger.info(f"Reached message limit ({max_messages}). Stopping worker...")
                self._stop_event.set()
                if self.streaming_pull_future:
                    self.streaming_pull_future.cancel()

    def run(
        self,
        max_messages: int | None = None,
        timeout: int | None = None,
        max_output_tokens: int | None = None,
    ):
        """Starts the worker's message consumption loop.

        This method initiates the subscription to the configured Pub/Sub topic
        and blocks, waiting for messages. It includes logic for graceful
        shutdown upon interruption or timeout.

        Args:
            max_messages: The maximum number of messages to process before stopping.
            timeout: The maximum time in seconds to wait for messages.
        """
        subscription_name = self.config.GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS
        if not subscription_name:
            self.logger.critical("Subscription name not configured. Worker cannot start.")
            return

        def callback(message: Message):
            self._message_callback(message, max_messages)

        self.streaming_pull_future = self.pubsub_provider.subscribe(subscription_name, callback)
        self.logger.info(f"Worker is now running and waiting for messages (timeout: {timeout}s)...")

        try:
            self.streaming_pull_future.result(timeout=timeout)
        except TimeoutError:
            self.logger.warning(f"Worker timed out after {timeout} seconds of inactivity.")
        except (GoogleAPICallError, KeyboardInterrupt) as e:
            self.logger.warning(f"Shutdown requested: {type(e).__name__}")
        except Exception as e:
            if "cancelled" not in str(e).lower():
                self.logger.critical(f"A critical error stopped the worker: {e}", exc_info=True)
        finally:
            self.logger.info("Stopping worker...")
            if self.streaming_pull_future and not self.streaming_pull_future.cancelled():
                self.streaming_pull_future.cancel()
                try:
                    self.streaming_pull_future.result(timeout=10)
                except Exception:  # nosec B110
                    pass
            self.logger.info("Worker has stopped gracefully.")
