"""Initializes the CLI application and constructs the command groups."""

import click
from public_detective.cli.analysis import analysis_group
from public_detective.cli.worker import worker_group


def create_cli() -> click.Group:
    """Create and configure the main CLI group with all subcommands.

    This function acts as a factory for the CLI application. It imports
    command groups from other modules and adds them to a root group.
    This modular structure allows for easy extension of the CLI.

    Returns:
        The main Click command group for the application.
    """

    @click.group()
    def cli() -> None:
        """A unified command-line interface for the Public Detective tool.

        This CLI provides a collection of commands to interact with the Public
        Detective system, allowing users to trigger analyses, manage tasks,
        and run workers.
        """
        pass

    cli.add_command(analysis_group)
    cli.add_command(worker_group)

    return cli
