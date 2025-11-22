from fastapi import APIRouter, Request
from ..templates_config import templates

from public_detective.web.services.analysis import AnalysisService

router = APIRouter(prefix="/analysis", tags=["analysis"])
analysis_service = AnalysisService()

@router.get("/{analysis_id}", name="analysis_detail")
async def analysis_detail(request: Request, analysis_id: str):
    analysis = analysis_service.get_analysis_details(analysis_id)
    if not analysis:
        # Handle 404 properly in a real app, for now just return basic template or error
        return templates.TemplateResponse("analysis.html", {"request": request, "error": "Analysis not found"})
    
    history = analysis_service.get_version_history(analysis["procurement_control_number"])
    
    return templates.TemplateResponse(
        "analysis.html", 
        {
            "request": request, 
            "analysis": analysis,
            "history": history
        }
    )
