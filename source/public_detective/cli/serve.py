import click
import uvicorn

@click.command("serve")
@click.option("--host", default="0.0.0.0", help="Host to bind the server to.")
@click.option("--port", default=8000, type=int, help="Port to bind the server to.")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development.")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the Public Detective web server."""
    click.echo(f"Starting server at http://{host}:{port}")
    uvicorn.run(
        "public_detective.web.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
