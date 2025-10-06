from pathlib import Path

from click.testing import CliRunner
from public_detective.cli import config
from public_detective.providers.config_manager import ConfigManager


def test_config_set_and_get(tmp_path: Path) -> None:
    """Tests setting and getting a simple key-value pair."""
    env_file = tmp_path / ".env"
    runner = CliRunner()

    # Set a value
    result = runner.invoke(
        config.set_value,
        ["TEST_KEY", "test_value", "--file", str(env_file)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert f"Set 'TEST_KEY' in {env_file}" in result.output

    # Get the value
    result = runner.invoke(config.get_value, ["TEST_KEY", "--file", str(env_file)], catch_exceptions=False)
    assert result.exit_code == 0
    assert result.output.strip() == "test_value"


def test_config_unset(tmp_path: Path) -> None:
    """Tests unsetting a key."""
    env_file = tmp_path / ".env"
    manager = ConfigManager(env_file)
    manager.set("TEST_KEY", "test_value")

    runner = CliRunner()
    result = runner.invoke(
        config.set_value,
        ["TEST_KEY", "--unset", "--file", str(env_file)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert f"Unset 'TEST_KEY' in {env_file}" in result.output

    # Verify it's gone
    result = runner.invoke(config.get_value, ["TEST_KEY", "--file", str(env_file)], catch_exceptions=False)
    assert result.exit_code != 0
    assert "not found" in result.output


def test_config_get_secret_masked(tmp_path: Path) -> None:
    """Tests that secret values are masked by default."""
    env_file = tmp_path / ".env"
    manager = ConfigManager(env_file)
    manager.set("MY_SECRET_KEY", "super_secret_value")

    runner = CliRunner()
    result = runner.invoke(config.get_value, ["MY_SECRET_KEY", "--file", str(env_file)], catch_exceptions=False)
    assert result.exit_code == 0
    assert "••••" in result.output
    assert "super_secret_value" not in result.output


def test_config_get_secret_raw(tmp_path: Path) -> None:
    """Tests that secret values are shown with the --raw flag."""
    env_file = tmp_path / ".env"
    manager = ConfigManager(env_file)
    manager.set("MY_SECRET_KEY", "super_secret_value")

    runner = CliRunner()
    result = runner.invoke(
        config.get_value,
        ["MY_SECRET_KEY", "--raw", "--file", str(env_file)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert result.output.strip() == "super_secret_value"


def test_config_list_secrets_masked(tmp_path: Path) -> None:
    """Tests that `list` masks secrets by default."""
    env_file = tmp_path / ".env"
    manager = ConfigManager(env_file)
    manager.set("REGULAR_KEY", "visible")
    manager.set("SECRET_TOKEN", "hidden")

    runner = CliRunner()
    result = runner.invoke(config.list_values, ["--file", str(env_file)], catch_exceptions=False)
    assert result.exit_code == 0
    assert "REGULAR_KEY=visible" in result.output
    assert "SECRET_TOKEN=••••" in result.output
    assert "hidden" not in result.output


def test_config_list_show_secrets_confirmed(tmp_path: Path) -> None:
    """Tests that `list --show-secrets` reveals secrets after confirmation."""
    env_file = tmp_path / ".env"
    manager = ConfigManager(env_file)
    manager.set("SECRET_TOKEN", "hidden")

    runner = CliRunner()
    result = runner.invoke(
        config.list_values,
        ["--show-secrets", "--file", str(env_file)],
        input="y\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "SECRET_TOKEN=hidden" in result.output


def test_config_list_empty(tmp_path: Path) -> None:
    """Tests `list` with no .env file."""
    env_file = tmp_path / ".env"
    runner = CliRunner()
    result = runner.invoke(config.list_values, ["--file", str(env_file)], catch_exceptions=False)
    assert result.exit_code == 0
    assert "No configuration found" in result.output


def test_config_get_not_found(tmp_path: Path) -> None:
    """Tests `get` for a key that doesn't exist."""
    env_file = tmp_path / ".env"
    runner = CliRunner()
    result = runner.invoke(config.get_value, ["NON_EXISTENT_KEY", "--file", str(env_file)])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_config_set_usage_errors() -> None:
    """Tests usage errors for the `set` command."""
    runner = CliRunner()

    # Using --unset with a value
    result = runner.invoke(config.set_value, ["KEY", "VALUE", "--unset"])
    assert result.exit_code != 0
    assert "Cannot use --unset with a value" in result.output

    # Not providing a value without --unset
    result = runner.invoke(config.set_value, ["KEY"])
    assert result.exit_code != 0
    assert "A value is required" in result.output


def test_config_list_show_secrets_yes(tmp_path: Path) -> None:
    """Tests that `list --show-secrets --yes` reveals secrets without a prompt."""
    env_file = tmp_path / ".env"
    manager = ConfigManager(env_file)
    manager.set("SECRET_TOKEN", "hidden")

    runner = CliRunner()
    result = runner.invoke(
        config.list_values,
        ["--show-secrets", "--yes", "--file", str(env_file)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "SECRET_TOKEN=hidden" in result.output
