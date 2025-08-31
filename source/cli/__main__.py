import click

from source.cli.commands import analyze, pre_analyze


@click.group()
def cli():
    """Public Detective CLI."""
    pass


cli.add_command(analyze)
cli.add_command(pre_analyze)

if __name__ == "__main__":
    cli()
