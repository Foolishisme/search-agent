from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = None


class SearchResult(BaseModel):
    title: str
    snippet: str
    url: str


class ExecutionPlan(BaseModel):
    route: Literal["direct_answer", "information_gathering", "python_execution"]
    canvas_requested: bool = False
    selected_skills: list[str] = Field(default_factory=list)
    rationale: str | None = None


class SearchDecision(BaseModel):
    next: Literal["answer", "retry", "stop"]
    reason: str | None = None
    query: str | None = None


class CanvasDraft(BaseModel):
    title: str
    content: str


class PythonScriptDraft(BaseModel):
    code: str
    rationale: str | None = None


class ToolCall(BaseModel):
    name: Literal["search_web", "save_markdown_artifact", "execute_python_wsl"]
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentAction(BaseModel):
    action: Literal["search", "canvas", "final"]
    query: str | None = None
    answer: str | None = None
    title: str | None = None
    content: str | None = None


class RuntimeLog(BaseModel):
    stage: Literal["input", "plan", "thought", "search", "python", "canvas", "final", "error"]
    message: str


class ToolObservation(BaseModel):
    step: int
    tool: Literal["search", "canvas", "search_web", "save_markdown_artifact", "execute_python_wsl"]
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


class RulesPayload(BaseModel):
    content: str = ""


class SkillSummary(BaseModel):
    seq: int
    skill_id: str
    name: str
    description: str
    enabled: bool = True


class SkillDetail(SkillSummary):
    content: str = ""


class SkillCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    content: str = ""
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Skill name cannot be blank")
        return normalized


class SkillUpdateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    content: str = ""
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Skill name cannot be blank")
        return normalized


class SkillContext(BaseModel):
    skill_id: str
    name: str
    description: str
    content: str
