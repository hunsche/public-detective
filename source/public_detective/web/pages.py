from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from public_detective.web.presentation import PresentationService
from pathlib import Path

router = APIRouter()

templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=templates_path)

@router.get("/", name="home")
def home(request: Request, service: PresentationService = Depends()):
    stats = service.get_home_stats()
    return templates.TemplateResponse("index.html", {"request": request, "stats": stats})

@router.get("/analyses", name="analyses")
def analyses(request: Request, q: str = "", page: int = 1, service: PresentationService = Depends()):
    if q:
        results = service.search_analyses(q, page=page)
    else:
        results = service.get_recent_analyses(page=page)
    
    context = {"request": request, "analyses": results, "q": q}
    
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/analysis_list.html", context)
    
    return templates.TemplateResponse("analyses.html", context)

@router.get("/analyses/{id}", name="analysis_detail")
def analysis_detail(request: Request, id: str, service: PresentationService = Depends()):
    analysis = service.get_analysis_details(id)
    if not analysis:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    
    return templates.TemplateResponse("analysis_detail.html", {"request": request, "analysis": analysis})

