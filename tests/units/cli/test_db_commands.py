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
def test_db_migrate_command_with_schema(mock_run: MagicMock) -> None:
    """Tests the db migrate command with schema."""
    runner = CliRunner()
    result = runner.invoke(db_group, ["migrate", "--schema", "test_schema"])
    assert result.exit_code == 0
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
def test_db_downgrade_command_with_schema(mock_run: MagicMock) -> None:
    """Tests the db downgrade command with schema."""
    runner = CliRunner()
    result = runner.invoke(db_group, ["downgrade", "--schema", "test_schema"], input="y\n")
    assert result.exit_code == 0
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
def test_db_reset_command_with_schema(mock_run: MagicMock) -> None:
    """Tests the db reset command with schema."""
    runner = CliRunner()
    result = runner.invoke(db_group, ["reset", "--schema", "test_schema"], input="y\n")
    assert result.exit_code == 0
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


@patch("public_detective.cli.db.subprocess.Popen")
@patch("public_detective.cli.db.ConfigProvider")
@patch("builtins.open", new_callable=MagicMock)
def test_db_populate_command_success(mock_open: MagicMock, mock_config: MagicMock, mock_popen: MagicMock) -> None:
    """Tests the db populate command."""
    mock_config.get_config.return_value.POSTGRES_PASSWORD = "password"  # nosec B105
    mock_config.get_config.return_value.POSTGRES_DB_SCHEMA = "public"
    mock_config.get_config.return_value.POSTGRES_HOST = "localhost"
    mock_config.get_config.return_value.POSTGRES_PORT = "5432"
    mock_config.get_config.return_value.POSTGRES_USER = "user"
    mock_config.get_config.return_value.POSTGRES_DB = "db"

    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"Success", b"")
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    mock_file = MagicMock()
    mock_file.read.return_value = "SQL DUMP"
    mock_open.return_value.__enter__.return_value = mock_file

    runner = CliRunner()
    with runner.isolated_filesystem():
        with open("tests/fixtures/seed.sql", "w") as f:
            f.write("SQL DUMP")

        # We need to mock open again because isolated_filesystem changes CWD
        # But since we are patching builtins.open, we need to be careful.
        # Actually, the code uses relative path "tests/fixtures/seed.sql".
        # If we run from root, it works. CliRunner isolated_filesystem changes CWD.
        # So the code won't find the file unless we create it in the isolated fs
        # AND the code looks for it there.
        # BUT the code hardcodes "tests/fixtures/seed.sql".
        # So we should probably NOT use isolated_filesystem if we want to rely on the path,
        # OR we should mock open to return content regardless of file existence.
        # Since we mocked open, we don't need real file.

        result = runner.invoke(db_group, ["populate"])

    assert result.exit_code == 0
    assert "Database populated successfully!" in result.output
    mock_popen.assert_called_once()


@patch("public_detective.cli.db.subprocess.Popen")
@patch("public_detective.cli.db.ConfigProvider")
@patch("builtins.open", new_callable=MagicMock)
def test_db_populate_command_file_not_found(
    mock_open: MagicMock, mock_config: MagicMock, mock_popen: MagicMock
) -> None:
    """Tests the db populate command when file is missing."""
    mock_open.side_effect = FileNotFoundError

    runner = CliRunner()
    result = runner.invoke(db_group, ["populate"])

    assert result.exit_code == 1
    assert "Error: Dump file tests/fixtures/seed.sql not found!" in result.output
