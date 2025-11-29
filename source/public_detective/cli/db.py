"""This module defines the 'db' command group for the Public Detective CLI."""

import subprocess  # nosec B404

import click


@click.group("db")
def db_group() -> None:
    """Groups commands related to database management."""
    pass


@db_group.command("migrate")
def migrate() -> None:
    """Runs database migrations to the latest version."""
    click.echo("Running database migrations...")
    try:
        subprocess.run(
            ["poetry", "run", "alembic", "upgrade", "head"],
            check=True,
        )  # nosec B603, B607
        click.secho("Migrations completed successfully!", fg="green")
    except subprocess.CalledProcessError as e:
        click.secho(f"An error occurred during migration: {e}", fg="red")
        raise click.Abort()


@db_group.command("downgrade")
def downgrade() -> None:
    """Downgrades the database to the previous version."""
    click.echo("Downgrading database...")
    try:
        subprocess.run(
            ["poetry", "run", "alembic", "downgrade", "-1"],
            check=True,
        )  # nosec B603, B607
        click.secho("Downgrade completed successfully!", fg="green")
    except subprocess.CalledProcessError as e:
        click.secho(f"An error occurred during downgrade: {e}", fg="red")
        raise click.Abort()


@db_group.command("reset")
def reset() -> None:
    """Resets the database by downgrading all migrations and then upgrading to the latest.

    Warning: This is a destructive operation and will result in data loss.
    """
    click.confirm(
        "Are you sure you want to reset the database? This will delete all data.",
        abort=True,
    )
    click.echo("Resetting database...")
    try:
        click.echo("Downgrading to base...")
        subprocess.run(
            ["poetry", "run", "alembic", "downgrade", "base"],
            check=True,
        )  # nosec B603, B607
        click.echo("Upgrading to head...")
        subprocess.run(
            ["poetry", "run", "alembic", "upgrade", "head"],
            check=True,
        )  # nosec B603, B607
        click.secho("Database reset successfully!", fg="green")
    except subprocess.CalledProcessError as e:
        click.secho(f"An error occurred during reset: {e}", fg="red")
        raise click.Abort()


@db_group.command("populate")
def populate() -> None:
    """Populates the database with the dump file."""
    click.echo("Populating database...")
    dump_file = "tests/fixtures/seed.sql"
    
    try:
        with open(dump_file, "r") as f:
            psql_process = subprocess.Popen(
                [
                    "docker", "compose", "exec", "-T", "postgres",
                    "psql", "-U", "postgres", "-d", "public_detective"
                ],
                stdin=f,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = psql_process.communicate()

            if psql_process.returncode != 0:
                click.secho(f"An error occurred during population: {stderr.decode()}", fg="red")
                raise click.Abort()
            
            click.echo(stdout.decode())
            click.secho("Database populated successfully!", fg="green")

    except FileNotFoundError:
        click.secho(f"Error: Dump file {dump_file} not found!", fg="red")
        raise click.Abort()
    except Exception as e:
        click.secho(f"An unexpected error occurred: {e}", fg="red")
        raise click.Abort()
