import click
import uvicorn
from public_detective.web.app import app

@click.command(name="serve")
@click.option("--host", default="0.0.0.0", help="Host to bind the server to.")
@click.option("--port", default=8000, help="Port to bind the server to.")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development.")
def serve_command(host: str, port: int, reload: bool) -> None:
    """Start the web server."""
    uvicorn.run(
        "public_detective.web.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
