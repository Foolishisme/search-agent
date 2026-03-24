from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.llm_client import DeepSeekClient
from app.logger import setup_logger
from app.runtime import AgentRuntime
from app.schemas import AskRequest, AskResponse
from app.search_tool import TavilySearchTool

BASE_DIR = Path(__file__).resolve().parent.parent
settings = get_settings()
setup_logger(settings.log_level)

app = FastAPI(title="Minimal Search Agent")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "templates")), name="static")

runtime = AgentRuntime(
    llm_client=DeepSeekClient(settings),
    search_tool=TavilySearchTool(settings),
)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)


@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    try:
        return await runtime.run(request.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
