"""Tests for the web command group."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from public_detective.cli.web import web_group


@patch("public_detective.cli.web.uvicorn.run")
def test_web_serve_command(mock_run: MagicMock) -> None:
    """Tests the web serve command."""
    runner = CliRunner()
    result = runner.invoke(web_group, ["serve"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        "public_detective.web.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )


@patch("public_detective.cli.web.uvicorn.run")
def test_web_serve_command_options(mock_run: MagicMock) -> None:
    """Tests the web serve command with options."""
    runner = CliRunner()
    result = runner.invoke(web_group, ["serve", "--host", "0.0.0.0", "--port", "9000", "--reload"])  # nosec B104
    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        "public_detective.web.main:app",
        host="0.0.0.0",  # nosec B104
        port=9000,
        reload=True,
        log_level="info",
    )
