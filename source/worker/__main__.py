from providers.logging import LoggingProvider
from worker.subscription import Subscription

logger = LoggingProvider().get_logger()

try:
    subscription = Subscription()
    subscription.run()
except KeyError as e:
    logger.critical(f"Execution stopped due to missing environment variables: {e}")
except Exception as e:
    logger.critical(
        f"An unhandled exception occurred at the top level: {e}", exc_info=True
    )
