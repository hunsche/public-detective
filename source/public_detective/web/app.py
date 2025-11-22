from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

app = FastAPI(
    title="Public Detective",
    description="AI-powered tool for enhancing transparency in public procurement.",
    version="1.0.0",
)

# Mount static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Import and include routers
from .routes import home, dashboard, analysis

app.include_router(home.router)
app.include_router(dashboard.router)
app.include_router(analysis.router)
