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
def main(max_messages: int | None):
    """
    Main entry point for the Pub/Sub worker.

    This script initializes and runs the Subscription worker, which listens for
    messages from a Pub/Sub subscription and processes them. The worker can be
    configured to exit after processing a specific number of messages using
    the --max-messages option.
    """
    try:
        subscription = Subscription()
        subscription.run(max_messages=max_messages)
    except KeyError as e:
        logger.critical(f"Execution stopped due to missing environment variables: {e}")
    except Exception as e:
        logger.critical(f"An unhandled exception occurred at the top level: {e}", exc_info=True)


main()
