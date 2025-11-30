"""Tests for the db command group."""

import subprocess  # nosec B404
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from public_detective.cli.db import db_group


@patch("public_detective.cli.db.subprocess.run")
def test_db_migrate_command_success(mock_run: MagicMock) -> None:
    """Tests the db migrate command."""
    runner = CliRunner()
    result = runner.invoke(db_group, ["migrate"])
    assert result.exit_code == 0
    assert "Migrations completed successfully!" in result.output
    mock_run.assert_called_once_with(["poetry", "run", "alembic", "upgrade", "head"], check=True)


@patch("public_detective.cli.db.subprocess.run")
def test_db_migrate_command_failure(mock_run: MagicMock) -> None:
    """Tests the db migrate command failure case."""
    runner = CliRunner()
    mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
    result = runner.invoke(db_group, ["migrate"])
    assert result.exit_code == 1
    assert "An error occurred during migration" in result.output


@patch("public_detective.cli.db.subprocess.run")
def test_db_downgrade_command_success(mock_run: MagicMock) -> None:
    """Tests the db downgrade command."""
    runner = CliRunner()
    result = runner.invoke(db_group, ["downgrade"], input="y\n")
    assert result.exit_code == 0
    assert "Downgrade completed successfully!" in result.output
    mock_run.assert_called_once_with(["poetry", "run", "alembic", "downgrade", "-1"], check=True)


@patch("public_detective.cli.db.subprocess.run")
def test_db_downgrade_command_failure(mock_run: MagicMock) -> None:
    """Tests the db downgrade command failure case."""
    runner = CliRunner()
    mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
    result = runner.invoke(db_group, ["downgrade"], input="y\n")
    assert result.exit_code == 1
    assert "An error occurred during downgrade" in result.output


@patch("public_detective.cli.db.subprocess.run")
def test_db_reset_command_success(mock_run: MagicMock) -> None:
    """Tests the db reset command."""
    runner = CliRunner()
    result = runner.invoke(db_group, ["reset"], input="y\n")
    assert result.exit_code == 0
    assert "Database reset successfully!" in result.output
    assert mock_run.call_count == 2
    mock_run.assert_any_call(["poetry", "run", "alembic", "downgrade", "base"], check=True)
    mock_run.assert_any_call(["poetry", "run", "alembic", "upgrade", "head"], check=True)


@patch("public_detective.cli.db.subprocess.run")
def test_db_reset_command_aborted(mock_run: MagicMock) -> None:
    """Tests aborting the db reset command."""
    runner = CliRunner()
    result = runner.invoke(db_group, ["reset"], input="n\n")
    assert result.exit_code == 1
    assert "Aborted!" in result.output
    mock_run.assert_not_called()


@patch("public_detective.cli.db.subprocess.run")
def test_db_reset_command_failure(mock_run: MagicMock) -> None:
    """Tests the db reset command failure case."""
    runner = CliRunner()
    mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
    result = runner.invoke(db_group, ["reset"], input="y\n")
    assert result.exit_code == 1
    assert "An error occurred during reset" in result.output
