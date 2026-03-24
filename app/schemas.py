from typing import Any, Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = None


class SearchResult(BaseModel):
    title: str
    snippet: str
    url: str


class AgentAction(BaseModel):
    action: Literal["search", "canvas", "final"]
    query: str | None = None
    answer: str | None = None
    title: str | None = None
    content: str | None = None


class RuntimeLog(BaseModel):
    stage: Literal["input", "thought", "search", "canvas", "final", "error"]
    message: str


class ToolObservation(BaseModel):
    step: int
    tool: Literal["search", "canvas"]
    status: Literal["success", "error"]
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class AttachmentMeta(BaseModel):
    attachment_id: str
    filename: str
    media_type: str
    size_bytes: int
    uploaded_at: str


class AttachmentContext(AttachmentMeta):
    excerpt: str
    content: str


class ArtifactSummary(BaseModel):
    artifact_id: str
    session_id: str
    title: str
    filename: str
    created_at: str
    updated_at: str


class ArtifactDetail(ArtifactSummary):
    content: str


class SessionTurn(BaseModel):
    created_at: str
    question: str
    answer: str
    need_search: bool
    query: str | None = None
    logs: list[RuntimeLog] = Field(default_factory=list)
    search_results: list[SearchResult] = Field(default_factory=list)
    tool_observations: list[ToolObservation] = Field(default_factory=list)


class SessionSummary(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    last_message_preview: str


class SessionDetail(SessionSummary):
    messages: list[ConversationMessage] = Field(default_factory=list)
    turns: list[SessionTurn] = Field(default_factory=list)
    latest_logs: list[RuntimeLog] = Field(default_factory=list)
    latest_search_results: list[SearchResult] = Field(default_factory=list)
    latest_tool_observations: list[ToolObservation] = Field(default_factory=list)
    attachments: list[AttachmentMeta] = Field(default_factory=list)


class AskResponse(BaseModel):
    session_id: str
    session_title: str
    answer: str
    need_search: bool
    query: str | None = None
    search_results: list[SearchResult] = Field(default_factory=list)
    logs: list[RuntimeLog] = Field(default_factory=list)
    tool_observations: list[ToolObservation] = Field(default_factory=list)
    conversation: list[ConversationMessage] = Field(default_factory=list)
    attachments: list[AttachmentMeta] = Field(default_factory=list)
