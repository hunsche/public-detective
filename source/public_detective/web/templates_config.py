from fastapi.templating import Jinja2Templates
from pathlib import Path
from . import strings

# Create a single shared instance of Jinja2Templates
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Inject strings into the global environment so they are available in all templates
templates.env.globals["strings"] = strings
