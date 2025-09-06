"""Main entry point for the CLI application."""

import click
from cli.commands import analyze, pre_analyze, retry, trigger_ranked_analysis


@click.group()
def cli() -> None:
    """A command-line interface for the Public Detective tool.

    This CLI provides a collection of commands to interact with the Public
    Detective system, allowing users to trigger analyses, manage tasks,
    and perform other administrative functions.
    """
    pass


cli.add_command(analyze)
cli.add_command(pre_analyze)
cli.add_command(retry)
cli.add_command(trigger_ranked_analysis)

if __name__ == "__main__":
    cli()
