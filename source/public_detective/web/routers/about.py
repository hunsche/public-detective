from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter()

# Define base path for templates
BASE_PATH = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))

@router.get("/sobre", name="about")
async def about(request: Request):
    """Página Sobre para demonstrar navegação."""
    return templates.TemplateResponse(
        "about.html",
        {
            "request": request,
            "title": "Sobre | Detetive Público"
        }
    )
