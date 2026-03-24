from app.artifact_store import MarkdownArtifactStore
from app.schemas import ArtifactDetail


SAVE_MARKDOWN_ARTIFACT_TOOL = {
    "type": "function",
    "function": {
        "name": "save_markdown_artifact",
        "description": "保存当前会话的 Markdown 文档；如果会话里还没有文档则创建，有文档则更新最近一份。",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "当前会话 ID",
                },
                "title": {
                    "type": "string",
                    "description": "Markdown 文档标题",
                },
                "content": {
                    "type": "string",
                    "description": "Markdown 文档完整内容",
                },
                "artifact_id": {
                    "type": "string",
                    "description": "可选。指定文档 ID 时更新该文档，不传时默认更新最近一份或创建新文档。",
                },
            },
            "required": ["session_id", "title", "content"],
        },
    },
}


def save_markdown_artifact(
    store: MarkdownArtifactStore,
    *,
    session_id: str,
    title: str,
    content: str,
    artifact_id: str | None = None,
) -> ArtifactDetail:
    return store.save_artifact(
        session_id=session_id,
        title=title,
        content=content,
        artifact_id=artifact_id,
    )
