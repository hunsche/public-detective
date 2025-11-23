"""This module defines the 'worker' command group for the Public Detective CLI."""

import click
from public_detective.providers.config import ConfigProvider
from public_detective.providers.logging import LoggingProvider
from public_detective.worker.subscription import Subscription


@click.group("worker")
def worker_group() -> None:
    """Groups commands related to the Pub/Sub worker."""
    pass


@worker_group.command("start")
@click.option(
    "--max-messages",
    type=int,
    default=None,
    help="Maximum number of messages to process before exiting.",
)
@click.option(
    "--timeout",
    type=int,
    default=None,
    help="Time in seconds to wait for a message. Defaults to 10s if --max-messages is set.",
)
@click.option(
    "--max-output-tokens",
    type=str,
    default=None,
    help="Maximum number of output tokens for the AI model. Set to 'None' to remove the limit.",
)
@click.option(
    "--gcs-path-prefix",
    default=None,
    help="[Internal Testing] Overwrites the base GCS path for uploads.",
)
@click.option(
    "--no-ai-tools",
    is_flag=True,
    default=False,
    help="[Internal Testing] Use the direct Gemini API without tools.",
)
@click.option(
    "--thinking-level",
    type=click.Choice(["LOW", "HIGH"], case_sensitive=False),
    default="HIGH",
    help="[Internal Testing] Set the AI thinking level.",
)
def start(
    max_messages: int | None,
    timeout: int | None,
    max_output_tokens: str | None,
    gcs_path_prefix: str | None,
    no_ai_tools: bool,
    thinking_level: str,
) -> None:
    """Initializes and runs the Pub/Sub subscription worker.

    Args:
        max_messages: Maximum number of messages to process before exiting.
        timeout: Time in seconds to wait for a message.
        max_output_tokens: Maximum number of output tokens for the AI model.
        gcs_path_prefix: Overwrites the base GCS path for uploads.
        no_ai_tools: Use the direct Gemini API without tools.
        thinking_level: The thinking level (LOW or HIGH).
    """
    logger = LoggingProvider().get_logger()
    if max_messages is not None and timeout is None:
        timeout = 10

    token_limit: int | None
    if max_output_tokens is None:
        token_limit = ConfigProvider.get_config().GCP_GEMINI_MAX_OUTPUT_TOKENS
    elif max_output_tokens.strip().lower() == "none":
        token_limit = None
    else:
        try:
            token_limit = int(max_output_tokens)
        except ValueError:
            logger.error(f"Invalid value for --max-output-tokens: '{max_output_tokens}'. Must be an integer or 'None'.")
            return

    try:
        subscription = Subscription(
            gcs_path_prefix=gcs_path_prefix,
            no_ai_tools=no_ai_tools,
            thinking_level=thinking_level,
        )
        subscription.run(
            max_messages=max_messages,
            timeout=timeout,
            max_output_tokens=token_limit,
        )
    except KeyError as e:
        logger.critical(f"Execution stopped due to missing environment variables: {e}")
    except Exception as e:
        logger.critical(f"An unhandled exception occurred at the top level: {e}", exc_info=True)
