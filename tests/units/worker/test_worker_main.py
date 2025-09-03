from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from source.worker.__main__ import main


@patch("source.worker.__main__.Subscription")
@patch("source.worker.__main__.ConfigProvider")
def test_main_success_with_defaults(mock_config_provider, mock_subscription):
    runner = CliRunner()
    result = runner.invoke(main, [])

    assert result.exit_code == 0
    mock_subscription.assert_called_once()
    mock_subscription.return_value.run.assert_called_once_with(
        max_messages=None,
        timeout=None,
        max_output_tokens=mock_config_provider.get_config.return_value.GCP_GEMINI_MAX_OUTPUT_TOKENS,
    )


@patch("source.worker.__main__.Subscription")
@patch("source.worker.__main__.ConfigProvider")
def test_main_success_with_args(mock_config_provider, mock_subscription):
    runner = CliRunner()
    result = runner.invoke(main, ["--max-messages", "10", "--timeout", "20", "--max-output-tokens", "100"])

    assert result.exit_code == 0
    mock_subscription.assert_called_once()
    mock_subscription.return_value.run.assert_called_once_with(
        max_messages=10,
        timeout=20,
        max_output_tokens=100,
    )


@patch("source.worker.__main__.Subscription")
@patch("source.worker.__main__.ConfigProvider")
def test_main_default_timeout(mock_config_provider, mock_subscription):
    runner = CliRunner()
    result = runner.invoke(main, ["--max-messages", "10"])

    assert result.exit_code == 0
    mock_subscription.assert_called_once()
    mock_subscription.return_value.run.assert_called_once_with(
        max_messages=10,
        timeout=10,
        max_output_tokens=mock_config_provider.get_config.return_value.GCP_GEMINI_MAX_OUTPUT_TOKENS,
    )


@patch("source.worker.__main__.Subscription")
@patch("source.worker.__main__.ConfigProvider")
def test_main_token_limit_none(mock_config_provider, mock_subscription):
    runner = CliRunner()
    result = runner.invoke(main, ["--max-output-tokens", "None"])

    assert result.exit_code == 0
    mock_subscription.assert_called_once()
    mock_subscription.return_value.run.assert_called_once_with(
        max_messages=None,
        timeout=None,
        max_output_tokens=None,
    )


@patch("source.worker.__main__.Subscription")
@patch("source.worker.__main__.ConfigProvider")
def test_main_token_limit_invalid(mock_config_provider, mock_subscription):
    runner = CliRunner()
    result = runner.invoke(main, ["--max-output-tokens", "invalid"])

    assert result.exit_code == 0
    mock_subscription.assert_not_called()


@patch("source.worker.__main__.Subscription", side_effect=KeyError("Test KeyError"))
@patch("source.worker.__main__.ConfigProvider")
def test_main_key_error(mock_config_provider, mock_subscription):
    runner = CliRunner()
    result = runner.invoke(main, [])

    assert result.exit_code == 0


@patch("source.worker.__main__.Subscription", side_effect=Exception("Test Exception"))
@patch("source.worker.__main__.ConfigProvider")
def test_main_exception(mock_config_provider, mock_subscription):
    runner = CliRunner()
    result = runner.invoke(main, [])

    assert result.exit_code == 0
