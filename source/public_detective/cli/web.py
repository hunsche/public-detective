import click
import uvicorn
from public_detective.web.main import app

@click.group(name="web")
def web_group():
    """Manage the web interface."""
    pass

@web_group.command(name="serve")
@click.option("--host", default="127.0.0.1", help="Host to bind to.")
@click.option("--port", default=8000, help="Port to bind to.")
@click.option("--reload", is_flag=True, help="Enable auto-reload.")
def serve(host: str, port: int, reload: bool):
    """Start the web server."""
    uvicorn.run(
        "public_detective.web.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
