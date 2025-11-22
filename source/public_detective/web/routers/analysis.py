from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from pathlib import Path
from public_detective.providers.database import DatabaseManager
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.repositories.procurements import ProcurementsRepository
from public_detective.providers.pubsub import PubSubProvider
from public_detective.providers.http import HttpProvider

router = APIRouter()

# Define base path for templates
BASE_PATH = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))

def get_analysis_repo():
    engine = DatabaseManager.get_engine()
    return AnalysisRepository(engine)

def get_procurement_repo():
    engine = DatabaseManager.get_engine()
    return ProcurementsRepository(engine, PubSubProvider(), HttpProvider())

@router.get("/analysis/{control_number}", name="analysis_detail")
async def analysis_detail(
    control_number: str,
    request: Request,
    analysis_repo: AnalysisRepository = Depends(get_analysis_repo),
    procurement_repo: ProcurementsRepository = Depends(get_procurement_repo)
):
    """Displays the full analysis detail (Dossier) for a procurement."""
    
    # Get the analysis
    analysis = analysis_repo.get_analysis_by_procurement(control_number)
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    # Get the procurement data
    procurement, _ = procurement_repo.get_procurement_by_control_number(control_number)
    
    if not procurement:
        raise HTTPException(status_code=404, detail="Procurement not found")
    
    return templates.TemplateResponse(
        "analysis_detail.html",
        {
            "request": request,
            "title": f"Análise: {procurement.government_entity.name}",
            "analysis": analysis,
            "procurement": procurement
        }
    )
