from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from ..templates_config import templates
from ..services.dashboard import DashboardService
from ..strings import strings

router = APIRouter(prefix="/dashboard")
dashboard_service = DashboardService()

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request, 
    q: str = None, 
    risk: str = None,
    city: str = None,
    state: str = None,
    category: str = None,
    start_date: str = None,
    end_date: str = None,
    modality: str = None,
    min_value: float = None,
    max_value: float = None,
    year: int = None,
    sphere: str = None,
    power: str = None
):
    stats = dashboard_service.get_stats()
    recent_activity = dashboard_service.get_recent_activity(
        search=q, 
        risk_level=risk,
        city=city,
        state=state,
        category=category,
        start_date=start_date,
        end_date=end_date,
        modality=modality,
        min_value=min_value,
        max_value=max_value,
        year=year,
        sphere=sphere,
        power=power
    )
    
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            "dashboard.html", 
            {"request": request, "recent_activity": recent_activity, "strings": strings},
            block_name="activity_list"
        )
        
    return templates.TemplateResponse(
        "dashboard.html", 
        {"request": request, "stats": stats, "recent_activity": recent_activity, "strings": strings}
    )
```
