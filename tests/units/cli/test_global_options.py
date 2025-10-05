"""Unit tests for the global CLI options."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from public_detective.cli import create_cli
from public_detective.providers.config import ConfigProvider


@pytest.fixture
def runner() -> CliRunner:
    """Returns a CliRunner for invoking the CLI."""
    return CliRunner()


@patch("public_detective.cli.analysis.AnalysisService")
def test_log_level_option(_: MagicMock, runner: CliRunner) -> None:
    """Tests that the --log-level option correctly sets the logger's level."""
    cli = create_cli()
    with patch("public_detective.cli.LoggingProvider") as mock_logging:
        mock_logger = MagicMock()
        mock_logging.return_value.get_logger.return_value = mock_logger

        result = runner.invoke(cli, ["--log-level", "DEBUG", "analysis", "prepare"])
        assert result.exit_code == 0
        mock_logger.setLevel.assert_called_once_with(logging.DEBUG)


@patch("public_detective.cli.analysis.AnalysisService")
def test_sync_option_forces_sync_mode(_: MagicMock, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests that the --sync flag correctly sets FORCE_SYNC to True."""
    cli = create_cli()
    monkeypatch.delenv("FORCE_SYNC", raising=False)

    config = ConfigProvider.get_config()
    assert not config.FORCE_SYNC, "Pre-condition: FORCE_SYNC should be False."

    result = runner.invoke(cli, ["--sync", "analysis", "prepare"])

    assert result.exit_code == 0

    config_after = ConfigProvider.get_config()
    assert config_after.FORCE_SYNC, "FORCE_SYNC should be True after --sync flag."


@patch("public_detective.cli.analysis.AnalysisService")
def test_default_log_level_is_used(_: MagicMock, runner: CliRunner) -> None:
    """Tests that the default log level is used when no flag is provided."""
    cli = create_cli()
    with patch("public_detective.cli.LoggingProvider") as mock_logging:
        mock_logger = MagicMock()
        mock_logging.return_value.get_logger.return_value = mock_logger

        result = runner.invoke(cli, ["analysis", "prepare"])
        assert result.exit_code == 0
        mock_logger.setLevel.assert_not_called()


@patch("public_detective.cli.analysis.AnalysisService")
def test_default_sync_mode_is_not_set(_: MagicMock, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests that FORCE_SYNC remains False when the --sync flag is not used."""
    cli = create_cli()
    monkeypatch.delenv("FORCE_SYNC", raising=False)

    config = ConfigProvider.get_config()
    assert not config.FORCE_SYNC, "Pre-condition: FORCE_SYNC should be False."

    result = runner.invoke(cli, ["analysis", "prepare"])

    assert result.exit_code == 0

    config_after = ConfigProvider.get_config()
    assert not config_after.FORCE_SYNC, "FORCE_SYNC should remain False without --sync flag."
