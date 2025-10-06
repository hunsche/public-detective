"""This module defines the 'config' command group for the Public Detective CLI."""

import click


@click.group("config")
def config_group() -> None:
    """Groups commands related to configuration management."""
    pass


@config_group.command("list")
@click.option("--show-secrets", is_flag=True, help="Show secret values without masking.")
@click.option("--yes", is_flag=True, help="Skip confirmation prompts.")
@click.option("--file", "env_file", type=click.Path(), default=".env", help="Path to the .env file.")
def list_values(show_secrets: bool, yes: bool, env_file: str) -> None:
    """Lists all configuration key-value pairs.

    Args:
        show_secrets: If True, shows secret values without masking.
        yes: If True, skips confirmation prompts.
        env_file: The path to the .env file.
    """
    from public_detective.providers.config_manager import ConfigManager
    from public_detective.providers.secrets import is_secret_key, mask_value

    config_manager = ConfigManager(env_file)
    config = config_manager.get_all()

    if not config:
        click.echo(f"No configuration found in {env_file}")
        return

    if show_secrets and not yes:
        if not click.confirm("Are you sure you want to show secret values?", abort=True):
            return

    click.echo(f"Configuration from {env_file}:")
    for key, value in config.items():
        if not show_secrets and is_secret_key(key):
            click.echo(f"{key}={mask_value(value)}")
        else:
            click.echo(f"{key}={value}")


@config_group.command("get")
@click.argument("key")
@click.option("--raw", is_flag=True, help="Show the raw value without masking.")
@click.option("--file", "env_file", type=click.Path(), default=".env", help="Path to the .env file.")
def get_value(key: str, raw: bool, env_file: str) -> None:
    """Gets a configuration value.

    Args:
        key: The configuration key to get.
        raw: If True, shows the raw value without masking.
        env_file: The path to the .env file.
    """
    from public_detective.providers.config_manager import ConfigManager
    from public_detective.providers.secrets import is_secret_key, mask_value

    config_manager = ConfigManager(env_file)
    value = config_manager.get(key)

    if value is None:
        click.secho(f"Key '{key}' not found in {env_file}", fg="red")
        raise click.Abort()

    if not raw and is_secret_key(key):
        click.echo(mask_value(value))
    else:
        click.echo(value)


@config_group.command("set")
@click.argument("key")
@click.argument("value", required=False)
@click.option("--unset", is_flag=True, help="Remove the configuration key.")
@click.option("--file", "env_file", type=click.Path(), default=".env", help="Path to the .env file.")
def set_value(key: str, value: str | None, unset: bool, env_file: str) -> None:
    """Sets or unsets a configuration value in the specified .env file.

    Args:
        key: The configuration key to set.
        value: The configuration value to set.
        unset: If True, removes the key.
        env_file: The path to the .env file.
    """
    from public_detective.providers.config_manager import ConfigManager

    if unset and value is not None:
        raise click.UsageError("Cannot use --unset with a value.")
    if not unset and value is None:
        raise click.UsageError("A value is required unless --unset is used.")

    config_manager = ConfigManager(env_file)

    if unset:
        config_manager.unset(key)
        click.secho(f"Unset '{key}' in {env_file}", fg="yellow")
    else:
        config_manager.set(key, value)
        click.secho(f"Set '{key}' in {env_file}", fg="green")
