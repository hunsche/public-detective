"""This module serves as the main entry point for the Pub/Sub worker.

It sets up a command-line interface using Click to start the subscription
listener. The worker's behavior, such as message limits and timeouts, can
be configured via CLI options.
"""

import click
from providers.config import ConfigProvider
from providers.logging import LoggingProvider
from worker.subscription import Subscription

logger = LoggingProvider().get_logger()


from source.providers.credentials import setup_google_credentials


@click.command()
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
def main(max_messages: int | None, timeout: int | None, max_output_tokens: str | None):
    setup_google_credentials()
    """
    Main entry point for the Pub/Sub worker.

    This script initializes and runs the Subscription worker. It can be configured
    to exit after a specific number of messages (--max-messages) or after a
    period of inactivity (--timeout). If --max-messages is used without a
    --timeout, a default timeout of 10 seconds is applied.
    """
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
        subscription = Subscription()
        subscription.run(max_messages=max_messages, timeout=timeout, max_output_tokens=token_limit)
    except KeyError as e:
        logger.critical(f"Execution stopped due to missing environment variables: {e}")
    except Exception as e:
        logger.critical(f"An unhandled exception occurred at the top level: {e}", exc_info=True)


main()
