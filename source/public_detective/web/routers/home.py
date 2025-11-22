from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from pathlib import Path
from public_detective.providers.database import DatabaseManager
from public_detective.repositories.analyses import AnalysisRepository

router = APIRouter()

# Define base path for templates
BASE_PATH = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))

def get_analysis_repo():
    engine = DatabaseManager.get_engine()
    return AnalysisRepository(engine)

@router.get("/", name="home")
async def home(
    request: Request,
    analysis_repo: AnalysisRepository = Depends(get_analysis_repo)
):
    """Render the home page with real stats."""
    stats = analysis_repo.get_dashboard_stats()
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "Detetive Público | Inteligência",
            "stats": stats
        }
    )
