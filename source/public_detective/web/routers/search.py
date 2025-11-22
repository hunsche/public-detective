from fastapi import APIRouter, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from pathlib import Path
from public_detective.providers.database import DatabaseManager
from public_detective.repositories.procurements import ProcurementsRepository
from public_detective.providers.pubsub import PubSubProvider
from public_detective.providers.http import HttpProvider

router = APIRouter()

# Define base path for templates
BASE_PATH = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))

def get_procurement_repo():
    engine = DatabaseManager.get_engine()
    # We need dummy providers for the repo init, though they aren't used for search
    # In a real app, use Dependency Injection properly
    return ProcurementsRepository(engine, PubSubProvider(), HttpProvider())

@router.post("/search", name="search")
async def search(
    request: Request,
    q: str = Form(...),
    date_from: str = Form(None),
    date_to: str = Form(None),
    state: str = Form(None),
    modality: str = Form(None),
    min_value: float = Form(None),
    max_value: float = Form(None),
    procurement_repo: ProcurementsRepository = Depends(get_procurement_repo)
):
    """Handles search requests with optional filters and returns a partial HTML."""
    results = procurement_repo.search_procurements(
        query=q,
        date_from=date_from,
        date_to=date_to,
        state=state,
        modality=modality,
        min_value=min_value,
        max_value=max_value
    )
    
    return templates.TemplateResponse(
        "partials/search_results.html",
        {
            "request": request,
            "results": results,
            "query": q
        }
    )
