"""This module defines the CLI commands for the ranking service."""

import click


@click.group()
def ranking() -> None:
    """Commands for the ranking service."""
    pass


@ranking.command()
def hello() -> None:
    """A simple command that prints a greeting."""
    click.echo("Hello from the ranking service!")
