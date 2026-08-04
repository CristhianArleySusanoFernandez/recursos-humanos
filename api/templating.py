# Instancia única de Jinja2Templates compartida por todos los routers.
# Importar desde aquí evita instanciar templates en múltiples sitios.

from pathlib import Path

from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
