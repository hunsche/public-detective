"""Web CLI commands."""

import click
import uvicorn


@click.group(name="web")
def web_group() -> None:
    """Manage the web interface."""
    pass


@web_group.command(name="serve")
@click.option("--host", default="127.0.0.1", help="Host to bind to.")
@click.option("--port", default=8000, help="Port to bind to.")
@click.option("--reload", is_flag=True, help="Enable auto-reload.")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the web server.

    Args:
        host: Host to bind to.
        port: Port to bind to.
        reload: Enable auto-reload.
    """
    uvicorn.run("public_detective.web.main:app", host=host, port=port, reload=reload, log_level="info")
