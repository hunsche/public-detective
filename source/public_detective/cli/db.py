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
