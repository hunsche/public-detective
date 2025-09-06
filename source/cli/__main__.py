import click

from source.cli.commands import analyze, pre_analyze, retry
from source.providers.credentials import setup_google_credentials


@click.group()
def cli():
    setup_google_credentials()
    """A command-line interface for the Public Detective tool.

    This CLI provides a collection of commands to interact with the Public
    Detective system, allowing users to trigger analyses, manage tasks,
    and perform other administrative functions.
    """
    pass


cli.add_command(analyze)
cli.add_command(pre_analyze)
cli.add_command(retry)

if __name__ == "__main__":
    cli()
