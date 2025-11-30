"""This module defines the 'db' command group for the Public Detective CLI."""

import os
import subprocess  # nosec B404

import click
from public_detective.providers.config import ConfigProvider


@click.group("db")
@click.option("--schema", default=None, help="The database schema to use.")
def db_group(schema: str | None) -> None:
    """Groups commands related to database management.

    Args:
        schema: The database schema to use.
    """
    if schema:
        os.environ["POSTGRES_DB_SCHEMA"] = schema


@db_group.command("migrate")
@click.option("--schema", default=None, help="The database schema to use.")
def migrate(schema: str | None) -> None:
    """Runs database migrations to the latest version.

    Args:
        schema: The database schema to use.
    """
    if schema:
        os.environ["POSTGRES_DB_SCHEMA"] = schema

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
@click.option("--schema", default=None, help="The database schema to use.")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def downgrade(schema: str | None, yes: bool) -> None:
    """Downgrades the database to the previous version.

    Args:
        schema: The database schema to use.
        yes: Skip confirmation prompt.
    """
    if not yes:
        click.confirm(
            "Warning: This is a destructive operation that may result in data loss "
            "(tables will be dropped). Are you sure you want to continue?",
            abort=True,
        )

    if schema:
        os.environ["POSTGRES_DB_SCHEMA"] = schema

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
@click.option("--schema", default=None, help="The database schema to use.")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def reset(schema: str | None, yes: bool) -> None:
    """Resets the database by downgrading all migrations and then upgrading to the latest.

    Warning: This is a destructive operation and will result in data loss.

    Args:
        schema: The database schema to use.
        yes: Skip confirmation prompt.
    """
    if not yes:
        click.confirm(
            "Are you sure you want to reset the database? This will delete all data.",
            abort=True,
        )
    if schema:
        os.environ["POSTGRES_DB_SCHEMA"] = schema
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
@click.option("--schema", default=None, help="The database schema to use.")
def populate(schema: str | None) -> None:
    """Populates the database with the dump file.

    Args:
        schema: The database schema to use.
    """
    if schema:
        os.environ["POSTGRES_DB_SCHEMA"] = schema

    config = ConfigProvider.get_config()

    click.echo("Populating database...")
    dump_file = "tests/fixtures/seed.sql"

    env = os.environ.copy()
    env["PGPASSWORD"] = config.POSTGRES_PASSWORD
    env["PGCLIENTENCODING"] = "UTF8"

    target_schema = schema or config.POSTGRES_DB_SCHEMA

    try:
        with open(dump_file, encoding="utf-8") as f:
            dump_content = f.read()

        if target_schema:
            input_content = f"SET search_path TO {target_schema};\n{dump_content}"
        else:
            input_content = dump_content

        click.echo(f"Input content length: {len(input_content)}")

        psql_process = subprocess.Popen(
            [
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                config.POSTGRES_HOST,
                "-p",
                config.POSTGRES_PORT,
                "-U",
                config.POSTGRES_USER,
                "-d",
                config.POSTGRES_DB,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )  # nosec B603, B607
        stdout, stderr = psql_process.communicate(input=input_content.encode("utf-8"))

        if stderr:
            click.secho(f"Stderr: {stderr.decode()}", fg="yellow")

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
