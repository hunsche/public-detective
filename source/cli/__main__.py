import click

from source.cli.commands import analyze_command, pre_analyze_command


@click.group()
def cli():
    pass


cli.add_command(analyze_command)
cli.add_command(pre_analyze_command)


if __name__ == "__main__":
    cli()
