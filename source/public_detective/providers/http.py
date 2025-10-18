"""This module provides a centralized HTTP client for the application."""

import time
from typing import Any

import requests
from public_detective.providers.config import Config, ConfigProvider
from public_detective.providers.logging import Logger, LoggingProvider
from requests.exceptions import ConnectTimeout, ReadTimeout
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential


class HttpProvider:
    """A centralized HTTP client that manages a requests.Session."""

    _session: requests.Session | None = None
    _config: Config
    _logger: Logger

    def __init__(self) -> None:
        """Initializes the HttpProvider."""
        self._config = ConfigProvider.get_config()
        self._logger = LoggingProvider().get_logger()

    def _get_session(self) -> requests.Session:
        """Initializes and returns a singleton requests.Session object.

        The session is configured to ignore system-level proxy settings by
        setting `trust_env` to `False`.

        Returns:
            A configured `requests.Session` instance.
        """
        if self._session is None:
            self._session = requests.Session()
            self._session.trust_env = False
            self._session.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/91.0.4472.124 Safari/537.36"
                    ),
                    "Connection": "close",
                }
            )
        return self._session

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=1, max=10),
        retry=(retry_if_exception_type(ConnectTimeout) | retry_if_exception_type(ReadTimeout)),
        reraise=True,
    )
    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """Performs a GET request with a retry mechanism.

        It uses a granular timeout of 5 seconds for the connection and 30
        seconds for the read.

        Args:
            url: The URL to request.
            **kwargs: Additional keyword arguments to pass to requests.get.

        Returns:
            The requests.Response object.
        """
        time.sleep(self._config.HTTP_REQUEST_DELAY_SECONDS)
        session = self._get_session()
        kwargs.setdefault("timeout", (5, 30))
        self._logger.debug(f"Fetching URL: {url} with params: {kwargs.get('params')}")
        response = session.get(url, **kwargs)
        self._logger.debug(f"Request to {response.url} completed with status: {response.status_code}")
        return response

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=1, max=10),
        retry=(retry_if_exception_type(ConnectTimeout) | retry_if_exception_type(ReadTimeout)),
        reraise=True,
    )
    def head(self, url: str, **kwargs: Any) -> requests.Response:
        """Performs a HEAD request with a retry mechanism.

        It uses a granular timeout of 5 seconds for the connection and 30
        seconds for the read.

        Args:
            url: The URL to request.
            **kwargs: Additional keyword arguments to pass to requests.head.

        Returns:
            The requests.Response object.
        """
        time.sleep(self._config.HTTP_REQUEST_DELAY_SECONDS)
        session = self._get_session()
        kwargs.setdefault("timeout", (5, 30))
        self._logger.debug(f"Fetching HEAD for URL: {url}")
        response = session.head(url, **kwargs)
        self._logger.debug(f"HEAD request to {response.url} completed with status: {response.status_code}")
        return response

    def close(self) -> None:
        """Closes the session."""
        if self._session:
            self._session.close()
            self._session = None
