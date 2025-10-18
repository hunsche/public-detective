"""Unit tests for the HttpProvider."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
import requests
from public_detective.providers.http import HttpProvider
from requests.exceptions import ConnectTimeout, ReadTimeout


@pytest.fixture
def mock_config() -> Generator[MagicMock, None, None]:
    """Fixture for a mocked ConfigProvider."""
    with patch("public_detective.providers.config.ConfigProvider.get_config") as mock_get_config:
        mock_config_instance = MagicMock()
        mock_config_instance.HTTP_REQUEST_DELAY_SECONDS = 0
        mock_get_config.return_value = mock_config_instance
        yield mock_config_instance


def test_get_session_creates_new_session(mock_config: MagicMock) -> None:
    """Tests that a new session is created if one doesn't exist."""
    provider = HttpProvider()
    session = provider._get_session()
    assert session is not None
    assert isinstance(session, requests.Session)
    assert provider._session is session


def test_get_session_returns_existing_session(mock_config: MagicMock) -> None:
    """Tests that an existing session is returned."""
    provider = HttpProvider()
    session1 = provider._get_session()
    session2 = provider._get_session()
    assert session1 is session2


@patch("requests.Session.get")
def test_get_successful(mock_get: MagicMock, mock_config: MagicMock) -> None:
    """Tests a successful GET request."""
    provider = HttpProvider()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    response = provider.get("http://example.com")
    assert response.status_code == 200
    mock_get.assert_called_once_with("http://example.com", timeout=(5, 30))


@patch("requests.Session.head")
def test_head_successful(mock_head: MagicMock, mock_config: MagicMock) -> None:
    """Tests a successful HEAD request."""
    provider = HttpProvider()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_head.return_value = mock_response

    response = provider.head("http://example.com", allow_redirects=True)
    assert response.status_code == 200
    mock_head.assert_called_once_with("http://example.com", timeout=(5, 30), allow_redirects=True)


@patch("requests.Session.get", side_effect=ConnectTimeout)
def test_get_retry_on_connect_timeout(mock_get: MagicMock, mock_config: MagicMock) -> None:
    """Tests that GET requests are retried on ConnectTimeout."""
    provider = HttpProvider()
    with pytest.raises(ConnectTimeout):
        provider.get("http://example.com")
    assert mock_get.call_count == 3


@patch("requests.Session.get", side_effect=ReadTimeout)
def test_get_retry_on_read_timeout(mock_get: MagicMock, mock_config: MagicMock) -> None:
    """Tests that GET requests are retried on ReadTimeout."""
    provider = HttpProvider()
    with pytest.raises(ReadTimeout):
        provider.get("http://example.com")
    assert mock_get.call_count == 3


@patch("requests.Session.head", side_effect=ConnectTimeout)
def test_head_retry_on_connect_timeout(mock_head: MagicMock, mock_config: MagicMock) -> None:
    """Tests that HEAD requests are retried on ConnectTimeout."""
    provider = HttpProvider()
    with pytest.raises(ConnectTimeout):
        provider.head("http://example.com")
    assert mock_head.call_count == 3


def test_close_session(mock_config: MagicMock) -> None:
    """Tests that the session is closed and set to None."""
    provider = HttpProvider()
    session = provider._get_session()
    assert provider._session is not None

    with patch.object(session, "close") as mock_close:
        provider.close()
        mock_close.assert_called_once()
        assert provider._session is None


def test_close_no_session(mock_config: MagicMock) -> None:
    """Tests that close does nothing if there is no session."""
    provider = HttpProvider()
    provider.close()
    assert provider._session is None
