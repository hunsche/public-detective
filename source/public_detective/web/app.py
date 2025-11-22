from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from public_detective.web.routers import home, search, analysis, about, demo

# Define base path
BASE_PATH = Path(__file__).resolve().parent

app = FastAPI(
    title="Public Detective",
    description="AI-powered tool for enhancing transparency in public procurement.",
    version="1.0.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(BASE_PATH / "static")), name="static")

# Initialize templates (globally accessible if needed, but usually in routers)
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))

# Include routers
app.include_router(home.router)
app.include_router(search.router)
app.include_router(analysis.router)
app.include_router(about.router)
app.include_router(demo.router)
