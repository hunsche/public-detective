"""This module initializes the CLI application."""

import click
from public_detective.cli.analysis import analysis_group
from public_detective.cli.config import config_group
from public_detective.cli.db import db_group
from public_detective.cli.ranking import ranking
from public_detective.cli.worker import worker_group
from public_detective.providers.logging import LoggingProvider


class Context:
    """A context object to pass global options to subcommands."""

    def __init__(self, output_format: str):
        """Initializes the context.

        Args:
            output_format: The desired output format (e.g., 'text', 'json').
        """
        self.output_format = output_format


def create_cli() -> click.Group:
    """Create and configure the main CLI group with all subcommands.

    This function acts as a factory for the CLI application. It imports
    command groups from other modules and adds them to a root group.
    This modular structure allows for easy extension of the CLI.

    Returns:
        The main Click command group for the application.
    """

    @click.group()
    @click.option(
        "--log-level",
        type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False),
        help="Override the default log level for this command.",
    )
    @click.option(
        "--sync",
        is_flag=True,
        help="Run tasks synchronously instead of asynchronously.",
    )
    @click.option(
        "--output",
        type=click.Choice(["text", "json", "yaml"], case_sensitive=False),
        default="text",
        help="Set the output format.",
    )
    @click.pass_context
    def cli(ctx: click.Context, log_level: str | None, sync: bool, output: str) -> None:
        """A unified command-line interface for the Public Detective tool.

        This CLI provides a collection of commands to interact with the Public
        Detective system, allowing users to trigger analyses, manage tasks,
        and run workers.

        Args:
            ctx: The Click context object.
            log_level: The desired logging level.
            sync: If True, forces synchronous execution.
            output: The desired output format.
        """
        LoggingProvider().get_logger(level_override=log_level)

        if sync:
            import os

            os.environ["FORCE_SYNC"] = "True"

        ctx.obj = Context(output_format=output)

    cli.add_command(analysis_group)
    cli.add_command(worker_group)
    cli.add_command(db_group)
    cli.add_command(config_group)
    cli.add_command(ranking)

    return cli
