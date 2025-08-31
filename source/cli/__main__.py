import click

from source.cli.commands import analyze, pre_analyze, reap_stale_tasks


@click.group()
def cli():
    """Public Detective CLI."""
    pass


cli.add_command(analyze)
cli.add_command(pre_analyze)
cli.add_command(reap_stale_tasks)

if __name__ == "__main__":
    cli()
