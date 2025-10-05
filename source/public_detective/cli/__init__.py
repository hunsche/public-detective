"""Initializes the CLI application and constructs the command groups."""

import logging

import click
from public_detective.cli.analysis import analysis_group
from public_detective.cli.config import config_group
from public_detective.cli.db import db_group
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
        "--verbose",
        is_flag=True,
        help="Enable verbose logging (INFO level).",
    )
    @click.option(
        "--debug",
        is_flag=True,
        help="Enable debug logging (DEBUG level).",
    )
    @click.option(
        "--output",
        type=click.Choice(["text", "json", "yaml"], case_sensitive=False),
        default="text",
        help="Set the output format.",
    )
    @click.pass_context
    def cli(ctx: click.Context, verbose: bool, debug: bool, output: str) -> None:
        """A unified command-line interface for the Public Detective tool.

        This CLI provides a collection of commands to interact with the Public
        Detective system, allowing users to trigger analyses, manage tasks,
        and run workers.

        Args:
            ctx: The Click context object.
            verbose: If True, sets logging level to INFO.
            debug: If True, sets logging level to DEBUG.
            output: The desired output format.
        """
        logger = LoggingProvider().get_logger()
        if debug:
            logger.setLevel(logging.DEBUG)
        elif verbose:
            logger.setLevel(logging.INFO)

        ctx.obj = Context(output_format=output)

    cli.add_command(analysis_group)
    cli.add_command(worker_group)
    cli.add_command(db_group)
    cli.add_command(config_group)

    return cli
