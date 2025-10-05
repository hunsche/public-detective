"""Tests for the config command group."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from public_detective.cli import create_cli


@patch("public_detective.cli.config.ConfigProvider.get_config")
def test_config_show_command(mock_get_config: MagicMock) -> None:
    """Tests the config show command."""
    # Arrange
    mock_config = MagicMock()
    mock_config.model_dump.return_value = {
        "LOG_LEVEL": "INFO",
        "GCP_PROJECT_ID": "test-project",
    }
    mock_get_config.return_value = mock_config

    runner = CliRunner()
    cli = create_cli()

    # Act
    result = runner.invoke(cli, ["config", "show"])

    # Assert
    assert result.exit_code == 0
    assert "LOG_LEVEL: INFO" in result.output
    assert "GCP_PROJECT_ID: test-project" in result.output


def test_config_set_command() -> None:
    """Tests the config set command."""
    runner = CliRunner()
    cli = create_cli()

    result = runner.invoke(cli, ["config", "set", "some_key", "some_value"])
    assert result.exit_code == 0
    assert "Setting configuration values is not yet implemented." in result.output
