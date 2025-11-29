"""Web pages router."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from public_detective.web.presentation import PresentationService

router = APIRouter()

templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=templates_path)


@router.get("/", name="home")
def home(request: Request, service: PresentationService = Depends()) -> Any:  # noqa: B008
    """Render the home page.

    Args:
        request: The request object.
        service: The presentation service.

    Returns:
        The rendered template response.
    """
    stats = service.get_home_stats()
    return templates.TemplateResponse("index.html", {"request": request, "stats": stats})


@router.get("/analyses", name="analyses")
def analyses(
    request: Request,
    query: str = "",
    page: int = 1,
    service: PresentationService = Depends(),  # noqa: B008
) -> Any:
    """Render the analyses list page.

    Args:
        request: The request object.
        query: The search query.
        page: The page number.
        service: The presentation service.

    Returns:
        The rendered template response.
    """
    if query:
        results = service.search_analyses(query, page=page)
    else:
        results = service.get_recent_analyses(page=page)

    context = {"request": request, "analyses": results, "q": query}

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/analysis_list.html", context)

    return templates.TemplateResponse("analyses.html", context)


@router.get("/analyses/{id}", name="analysis_detail")
def analysis_detail(request: Request, analysis_id: str, service: PresentationService = Depends()) -> Any:  # noqa: B008
    """Render the analysis detail page.

    Args:
        request: The request object.
        analysis_id: The analysis ID.
        service: The presentation service.

    Returns:
        The rendered template response.
    """
    analysis = service.get_analysis_details(analysis_id)
    if not analysis:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    return templates.TemplateResponse("analysis_detail.html", {"request": request, "analysis": analysis})
