from fastapi import APIRouter, Request
from ..templates_config import templates

router = APIRouter()

@router.get("/", name="home")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
