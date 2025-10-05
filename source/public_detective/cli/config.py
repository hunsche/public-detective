"""This module defines the 'config' command group for the Public Detective CLI."""

import click
from public_detective.providers.config import ConfigProvider


@click.group("config")
def config_group() -> None:
    """Groups commands related to configuration management."""
    pass


@config_group.command("show")
def show() -> None:
    """Shows the current configuration.

    This command prints the configuration values that are currently in use.
    """
    config = ConfigProvider.get_config()
    click.echo("Current configuration:")
    for key, value in config.model_dump().items():
        click.echo(f"{key}: {value}")


@config_group.command("set")
@click.argument("key")
@click.argument("value")
def set_value(key: str, value: str) -> None:
    """Sets a configuration value.

    This command is not yet implemented.

    Args:
        key: The configuration key to set.
        value: The configuration value to set.
    """
    click.echo("Setting configuration values is not yet implemented.")
