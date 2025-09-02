import time
from functools import wraps
from typing import Any, Callable

from providers.logging import LoggingProvider

logger = LoggingProvider().get_logger()


def retry_with_backoff(max_retries: int = 3, backoff_factor: float = 2.0, total_timeout: int = 60) -> Callable:
    """A decorator to retry a function with exponential backoff and a total timeout.

    Args:
        max_retries: The maximum number of retries (e.g., 3 means 1 initial call + 2 retries).
        backoff_factor: The factor to determine the sleep time.
        total_timeout: The total time in seconds to keep retrying.

    Returns:
        The decorator.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            retries = 0
            while retries < max_retries:
                if time.time() - start_time > total_timeout:
                    logger.error(f"Function {func.__name__} exceeded total timeout of {total_timeout}s.")
                    raise Exception(f"Total retry timeout of {total_timeout}s exceeded for {func.__name__}")

                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        logger.error(f"Function {func.__name__} failed after {max_retries} retries.")
                        raise
                    sleep_time = backoff_factor * (2 ** (retries - 1))
                    logger.warning(
                        f"Function {func.__name__} failed with {e}. "
                        f"Retrying in {sleep_time:.2f} seconds... ({retries}/{max_retries})"
                    )
                    time.sleep(sleep_time)

        return wrapper

    return decorator
