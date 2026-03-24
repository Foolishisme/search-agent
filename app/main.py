from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.llm_client import DeepSeekClient
from app.logger import setup_logger
from app.runtime import AgentRuntime
from app.schemas import AskRequest, AskResponse, SessionDetail, SessionSummary
from app.session_store import MarkdownSessionStore, SessionStoreError
from app.search_tool import TavilySearchTool

BASE_DIR = Path(__file__).resolve().parent.parent
settings = get_settings()
setup_logger(settings.log_level)

app = FastAPI(title="Minimal Search Agent")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "templates")), name="static")
session_store = MarkdownSessionStore(BASE_DIR / "target" / "sessions")

runtime = AgentRuntime(
    llm_client=DeepSeekClient(settings),
    search_tool=TavilySearchTool(settings),
)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)


@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    existing_session = None
    if request.session_id:
        existing_session = session_store.get_session(request.session_id)
        if existing_session is None:
            raise HTTPException(status_code=404, detail="会话不存在")

    try:
        response = await runtime.run(
            request.question,
            conversation=existing_session.messages if existing_session else [],
        )
        session = session_store.append_turn(
            request.session_id,
            request.question,
            response.answer,
            need_search=response.need_search,
            query=response.query,
            logs=response.logs,
            search_results=response.search_results,
        )
        response.session_id = session.session_id
        response.session_title = session.title
        response.conversation = session.messages
        return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except SessionStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/sessions", response_model=list[SessionSummary])
async def list_sessions() -> list[SessionSummary]:
    return session_store.list_sessions()


@app.get("/api/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str) -> SessionDetail:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@app.delete("/api/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str) -> Response:
    if not session_store.delete_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
