import json
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.attachment_store import AttachmentStore, AttachmentStoreError
from app.artifact_store import ArtifactStoreError, MarkdownArtifactStore
from app.config import get_settings
from app.llm_client import DeepSeekClient
from app.logger import setup_logger
from app.runtime import AgentRuntime
from app.schemas import ArtifactDetail, ArtifactSummary, AskRequest, AskResponse, SessionDetail, SessionSummary
from app.session_store import MarkdownSessionStore, SessionStoreError
from app.search_tool import TavilySearchTool

BASE_DIR = Path(__file__).resolve().parent.parent
settings = get_settings()
setup_logger(settings.log_level)

app = FastAPI(title="Minimal Search Agent")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "templates")), name="static")
session_store = MarkdownSessionStore(BASE_DIR / "target" / "sessions")
attachment_store = AttachmentStore(BASE_DIR / "target" / "uploads")
artifact_store = MarkdownArtifactStore(BASE_DIR / "target" / "artifacts")

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
        attachments = (
            attachment_store.list_attachment_contexts(request.session_id)
            if request.session_id
            else []
        )
        response = await runtime.run(
            request.question,
            conversation=existing_session.messages if existing_session else [],
            attachments=attachments,
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
        response.attachments = attachment_store.list_attachments(session.session_id)
        return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except SessionStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except AttachmentStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ask/stream")
async def ask_stream(
    question: str = Form(...),
    session_id: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
) -> StreamingResponse:
    existing_session = None
    if session_id:
        existing_session = session_store.get_session(session_id)
        if existing_session is None:
            raise HTTPException(status_code=404, detail="会话不存在")

    uploads = [upload for upload in files if upload.filename]
    effective_session_id = session_id or (uuid4().hex if uploads else None)

    try:
        if uploads:
            if effective_session_id is None:
                effective_session_id = uuid4().hex
            upload_payloads: list[tuple[str, str | None, bytes]] = []
            for upload in uploads:
                upload_payloads.append((upload.filename or "attachment", upload.content_type, await upload.read()))
            attachment_store.save_files(effective_session_id, upload_payloads)
        attachment_contexts = (
            attachment_store.list_attachment_contexts(effective_session_id)
            if effective_session_id
            else []
        )
    except AttachmentStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def stream_events():
        runtime_response: AskResponse | None = None
        try:
            if attachment_contexts:
                yield _json_line(
                    {
                        "type": "attachments",
                        "attachments": [item.model_dump(mode="json") for item in attachment_store.list_attachments(effective_session_id)],
                    }
                )

            async for event in runtime.run_stream(
                question,
                conversation=existing_session.messages if existing_session else [],
                attachments=attachment_contexts,
            ):
                if event["type"] == "final_response":
                    runtime_response = event["data"]
                    session = session_store.append_turn(
                        effective_session_id,
                        question,
                        runtime_response.answer,
                        need_search=runtime_response.need_search,
                        query=runtime_response.query,
                        logs=runtime_response.logs,
                        search_results=runtime_response.search_results,
                    )
                    runtime_response.session_id = session.session_id
                    runtime_response.session_title = session.title
                    runtime_response.conversation = session.messages
                    runtime_response.attachments = attachment_store.list_attachments(session.session_id)
                    yield _json_line(
                        {
                            "type": "final",
                            "data": runtime_response.model_dump(mode="json"),
                        }
                    )
                    return

                payload = event.copy()
                if "log" in payload:
                    payload["log"] = payload["log"].model_dump(mode="json")
                yield _json_line(payload)
        except (RuntimeError, ValueError, SessionStoreError, AttachmentStoreError) as exc:
            if runtime_response is None and uploads and session_id is None and effective_session_id:
                attachment_store.delete_session(effective_session_id)
            yield _json_line({"type": "error", "message": str(exc)})

    return StreamingResponse(stream_events(), media_type="application/x-ndjson")


@app.get("/api/sessions", response_model=list[SessionSummary])
async def list_sessions() -> list[SessionSummary]:
    return session_store.list_sessions()


@app.get("/api/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str) -> SessionDetail:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    session.attachments = attachment_store.list_attachments(session_id)
    return session


@app.delete("/api/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str) -> Response:
    if not session_store.delete_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    attachment_store.delete_session(session_id)
    artifact_store.delete_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/sessions/{session_id}/artifacts", response_model=list[ArtifactSummary])
async def list_artifacts(session_id: str) -> list[ArtifactSummary]:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return artifact_store.list_artifacts(session_id)


@app.post("/api/sessions/{session_id}/artifacts", response_model=ArtifactDetail)
async def create_artifact(session_id: str, payload: dict) -> ArtifactDetail:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    try:
        return artifact_store.create_artifact(
            session_id,
            str(payload.get("title", "")),
            str(payload.get("content", "")),
        )
    except ArtifactStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/sessions/{session_id}/artifacts/{artifact_id}", response_model=ArtifactDetail)
async def get_artifact(session_id: str, artifact_id: str) -> ArtifactDetail:
    detail = artifact_store.get_artifact(session_id, artifact_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return detail


@app.put("/api/sessions/{session_id}/artifacts/{artifact_id}", response_model=ArtifactDetail)
async def update_artifact(session_id: str, artifact_id: str, payload: dict) -> ArtifactDetail:
    try:
        return artifact_store.update_artifact(
            session_id,
            artifact_id,
            str(payload.get("title", "")),
            str(payload.get("content", "")),
        )
    except ArtifactStoreError as exc:
        detail = str(exc)
        status_code = 404 if detail == "文档不存在" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@app.get("/api/sessions/{session_id}/artifacts/{artifact_id}/download")
async def download_artifact(session_id: str, artifact_id: str) -> FileResponse:
    artifact_path = artifact_store.get_artifact_path(session_id, artifact_id)
    if artifact_path is None or not artifact_path.exists():
        raise HTTPException(status_code=404, detail="文档不存在")
    return FileResponse(
        artifact_path,
        media_type="text/markdown; charset=utf-8",
        filename=artifact_path.name,
    )


def _json_line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"
