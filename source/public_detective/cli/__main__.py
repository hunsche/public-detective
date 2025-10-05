"""Main entry point for the unified CLI application."""

from public_detective.cli import create_cli

cli = create_cli()


def main() -> None:
    """CLI entry point."""
    cli()


if __name__ == "__main__":
    main()
