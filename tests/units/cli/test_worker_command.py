from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from public_detective.cli.worker import worker_group


@patch("public_detective.cli.worker.Subscription")
@patch("public_detective.cli.worker.ConfigProvider")
@patch("public_detective.cli.worker.LoggingProvider")
def test_worker_start_defaults(
    mock_logging_provider: MagicMock,  # noqa: F841
    mock_config_provider: MagicMock,
    mock_subscription: MagicMock,
) -> None:
    """Test that the worker starts with default values."""
    runner = CliRunner()
    mock_config_instance = MagicMock()
    mock_config_instance.GCP_GEMINI_MAX_OUTPUT_TOKENS = 8192
    mock_config_provider.get_config.return_value = mock_config_instance

    mock_sub_instance = MagicMock()
    mock_subscription.return_value = mock_sub_instance

    result = runner.invoke(worker_group, ["start"])

    assert result.exit_code == 0
    mock_subscription.assert_called_once()
    mock_sub_instance.run.assert_called_once_with(max_messages=None, timeout=None, max_output_tokens=8192)


@patch("public_detective.cli.worker.Subscription")
@patch("public_detective.cli.worker.ConfigProvider")
@patch("public_detective.cli.worker.LoggingProvider")
def test_worker_start_with_max_messages(
    mock_logging_provider: MagicMock,  # noqa: F841
    mock_config_provider: MagicMock,  # noqa: F841
    mock_subscription: MagicMock,
) -> None:
    """Test that providing max-messages sets a default timeout."""
    runner = CliRunner()
    mock_sub_instance = MagicMock()
    mock_subscription.return_value = mock_sub_instance

    mock_config_instance = MagicMock()
    mock_config_instance.GCP_GEMINI_MAX_OUTPUT_TOKENS = 8192
    mock_config_provider.get_config.return_value = mock_config_instance

    result = runner.invoke(worker_group, ["start", "--max-messages", "10"])

    assert result.exit_code == 0
    mock_sub_instance.run.assert_called_once_with(max_messages=10, timeout=10, max_output_tokens=8192)


@patch("public_detective.cli.worker.Subscription")
@patch("public_detective.cli.worker.ConfigProvider")
@patch("public_detective.cli.worker.LoggingProvider")
def test_worker_start_with_max_output_tokens_none(
    mock_logging_provider: MagicMock,  # noqa: F841
    mock_config_provider: MagicMock,  # noqa: F841
    mock_subscription: MagicMock,
) -> None:
    """Test that max-output-tokens can be explicitly set to 'None'."""
    runner = CliRunner()
    mock_sub_instance = MagicMock()
    mock_subscription.return_value = mock_sub_instance

    result = runner.invoke(worker_group, ["start", "--max-output-tokens", "None"])

    assert result.exit_code == 0
    mock_sub_instance.run.assert_called_once_with(max_messages=None, timeout=None, max_output_tokens=None)


@patch("public_detective.cli.worker.Subscription")
@patch("public_detective.cli.worker.ConfigProvider")
@patch("public_detective.cli.worker.LoggingProvider")
def test_worker_start_with_max_output_tokens_int(
    mock_logging_provider: MagicMock,  # noqa: F841
    mock_config_provider: MagicMock,  # noqa: F841
    mock_subscription: MagicMock,
) -> None:
    """Test that max-output-tokens can be set to an integer."""
    runner = CliRunner()
    mock_sub_instance = MagicMock()
    mock_subscription.return_value = mock_sub_instance

    result = runner.invoke(worker_group, ["start", "--max-output-tokens", "2048"])

    assert result.exit_code == 0
    mock_sub_instance.run.assert_called_once_with(max_messages=None, timeout=None, max_output_tokens=2048)


@patch("public_detective.cli.worker.Subscription")
@patch("public_detective.cli.worker.ConfigProvider")
@patch("public_detective.cli.worker.logger")
def test_worker_start_invalid_max_output_tokens(
    mock_logger: MagicMock,
    mock_config_provider: MagicMock,  # noqa: F841
    mock_subscription: MagicMock,
) -> None:
    """Test that an invalid max-output-tokens value is handled."""
    runner = CliRunner()

    result = runner.invoke(worker_group, ["start", "--max-output-tokens", "invalid"])

    assert result.exit_code == 0
    mock_subscription.assert_not_called()
    mock_logger.error.assert_called_once_with(
        "Invalid value for --max-output-tokens: 'invalid'. Must be an integer or 'None'."
    )


@patch("public_detective.cli.worker.Subscription")
@patch("public_detective.cli.worker.ConfigProvider")
@patch("public_detective.cli.worker.logger")
def test_worker_start_key_error(
    mock_logger: MagicMock,
    mock_config_provider: MagicMock,  # noqa: F841
    mock_subscription: MagicMock,
) -> None:
    """Test that a KeyError during subscription is handled."""
    runner = CliRunner()

    mock_sub_instance = MagicMock()
    mock_sub_instance.run.side_effect = KeyError("Test KeyError")
    mock_subscription.return_value = mock_sub_instance

    result = runner.invoke(worker_group, ["start"])

    assert result.exit_code == 0
    mock_logger.critical.assert_called_once_with(
        "Execution stopped due to missing environment variables: 'Test KeyError'"
    )


@patch("public_detective.cli.worker.Subscription")
@patch("public_detective.cli.worker.ConfigProvider")
@patch("public_detective.cli.worker.logger")
def test_worker_start_generic_exception(
    mock_logger: MagicMock,
    mock_config_provider: MagicMock,  # noqa: F841
    mock_subscription: MagicMock,
) -> None:
    """Test that a generic Exception during subscription is handled."""
    runner = CliRunner()

    mock_sub_instance = MagicMock()
    mock_sub_instance.run.side_effect = Exception("Test Exception")
    mock_subscription.return_value = mock_sub_instance

    result = runner.invoke(worker_group, ["start"])

    assert result.exit_code == 0
    mock_logger.critical.assert_called_once_with(
        "An unhandled exception occurred at the top level: Test Exception", exc_info=True
    )
