"""Tests for the db command group."""

import subprocess  # nosec B404
from unittest.mock import MagicMock, patch

import pytest
from click.exceptions import Abort
from public_detective.cli.db import downgrade, migrate, reset


@patch("public_detective.cli.db.subprocess.run")
def test_db_migrate_command_success(mock_run: MagicMock) -> None:
    """Tests the db migrate command."""
    migrate.callback()
    mock_run.assert_called_once_with(["poetry", "run", "alembic", "upgrade", "head"], check=True)


@patch("public_detective.cli.db.subprocess.run")
def test_db_migrate_command_failure(mock_run: MagicMock) -> None:
    """Tests the db migrate command failure case."""
    mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
    with pytest.raises(Abort):
        migrate.callback()


@patch("public_detective.cli.db.subprocess.run")
def test_db_downgrade_command_success(mock_run: MagicMock) -> None:
    """Tests the db downgrade command."""
    downgrade.callback()
    mock_run.assert_called_once_with(["poetry", "run", "alembic", "downgrade", "-1"], check=True)


@patch("public_detective.cli.db.subprocess.run")
def test_db_downgrade_command_failure(mock_run: MagicMock) -> None:
    """Tests the db downgrade command failure case."""
    mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
    with pytest.raises(Abort):
        downgrade.callback()


@patch("public_detective.cli.db.subprocess.run")
def test_db_reset_command_success(mock_run: MagicMock) -> None:
    """Tests the db reset command."""
    with patch("click.confirm") as mock_confirm:
        mock_confirm.return_value = True
        reset.callback()
        assert mock_run.call_count == 2
        mock_run.assert_any_call(["poetry", "run", "alembic", "downgrade", "base"], check=True)
        mock_run.assert_any_call(["poetry", "run", "alembic", "upgrade", "head"], check=True)


@patch("public_detective.cli.db.subprocess.run")
def test_db_reset_command_aborted(mock_run: MagicMock) -> None:
    """Tests aborting the db reset command."""
    with patch("click.confirm") as mock_confirm:
        mock_confirm.side_effect = Abort
        with pytest.raises(Abort):
            reset.callback()
        mock_run.assert_not_called()


@patch("public_detective.cli.db.subprocess.run")
def test_db_reset_command_failure(mock_run: MagicMock) -> None:
    """Tests the db reset command failure case."""
    with patch("click.confirm") as mock_confirm:
        mock_confirm.return_value = True
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
        with pytest.raises(Abort):
            reset.callback()
