"""Unit tests for the main CLI entry point."""

from unittest.mock import patch

from click.testing import CliRunner


def test_cli_group_invoked_without_command() -> None:
    """Tests that invoking the CLI without a command shows help and exits."""
    from public_detective.cli.__main__ import cli  # Local import

    runner = CliRunner()
    result = runner.invoke(cli)
    assert result.exit_code != 0
    assert "Usage:" in result.output


def test_cli_group_help() -> None:
    """Tests that the --help option works on the base command."""
    from public_detective.cli.__main__ import cli  # Local import

    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "A unified command-line interface for the Public Detective tool." in result.output


def test_main_invokes_main() -> None:
    """
    Tests that the main function calls the cli.
    """
    from public_detective.cli.__main__ import main

    with patch("public_detective.cli.__main__.cli") as mock_cli:
        main()
        mock_cli.assert_called_once()
