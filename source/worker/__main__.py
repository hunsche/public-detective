import click
from providers.logging import LoggingProvider
from worker.subscription import Subscription

logger = LoggingProvider().get_logger()


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
def main(max_messages: int | None, timeout: int | None):
    """
    Main entry point for the Pub/Sub worker.

    This script initializes and runs the Subscription worker. It can be configured
    to exit after a specific number of messages (--max-messages) or after a
    period of inactivity (--timeout). If --max-messages is used without a
    --timeout, a default timeout of 10 seconds is applied.
    """
    # Apply default timeout only when a message limit is set
    if max_messages is not None and timeout is None:
        timeout = 10

    try:
        subscription = Subscription()
        subscription.run(max_messages=max_messages, timeout=timeout)
    except KeyError as e:
        logger.critical(f"Execution stopped due to missing environment variables: {e}")
    except Exception as e:
        logger.critical(f"An unhandled exception occurred at the top level: {e}", exc_info=True)


main()
