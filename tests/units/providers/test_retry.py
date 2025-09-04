from unittest.mock import MagicMock, patch

import pytest

from source.providers.retry import retry_with_backoff


def test_retry_success_on_first_try():
    """Tests that the decorated function succeeds on the first try."""
    mock_func = MagicMock(return_value="success")

    @retry_with_backoff()
    def decorated_func():
        return mock_func()

    result = decorated_func()

    assert result == "success"
    mock_func.assert_called_once()


def test_retry_fails_then_succeeds():
    """Tests that the decorator retries on failure and then succeeds."""
    mock_func = MagicMock(side_effect=[Exception("fail"), "success"])

    @retry_with_backoff(max_retries=2, backoff_factor=0.1)
    def decorated_func():
        return mock_func()

    result = decorated_func()

    assert result == "success"
    assert mock_func.call_count == 2


def test_retry_exceeds_max_retries():
    """Tests that the decorator raises an exception after exceeding max retries."""
    mock_func = MagicMock(side_effect=Exception("fail"))

    @retry_with_backoff(max_retries=3, backoff_factor=0.1)
    def decorated_func():
        return mock_func()

    with pytest.raises(Exception, match="fail"):
        decorated_func()

    assert mock_func.call_count == 3


@patch("time.sleep", return_value=None)
def test_retry_exceeds_timeout(_mock_sleep):
    """Tests that the decorator raises an exception after exceeding the total timeout."""
    mock_func = MagicMock(side_effect=Exception("fail"))

    @retry_with_backoff(max_retries=5, total_timeout=0.1)
    def decorated_func():
        return mock_func()

    with patch("time.time", side_effect=[0, 0.05, 0.2, 0.3, 0.4, 0.5, 0.6]):
        with pytest.raises(Exception, match="Total retry timeout of 0.1s exceeded"):
            decorated_func()
