"""Main web application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from public_detective.web import pages
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

app = FastAPI(title="Detetive Público")
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")


static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")


templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=templates_path)

app.include_router(pages.router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Status dictionary.
    """
    return {"status": "ok"}
