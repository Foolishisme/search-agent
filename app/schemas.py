from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = None


class SearchResult(BaseModel):
    title: str
    snippet: str
    url: str


class AgentAction(BaseModel):
    action: Literal["search", "final"]
    query: str | None = None
    answer: str | None = None


class RuntimeLog(BaseModel):
    stage: Literal["input", "thought", "search", "final", "error"]
    message: str


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class SessionTurn(BaseModel):
    created_at: str
    question: str
    answer: str
    need_search: bool
    query: str | None = None
    logs: list[RuntimeLog] = Field(default_factory=list)
    search_results: list[SearchResult] = Field(default_factory=list)


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


class AskResponse(BaseModel):
    session_id: str
    session_title: str
    answer: str
    need_search: bool
    query: str | None = None
    search_results: list[SearchResult] = Field(default_factory=list)
    logs: list[RuntimeLog] = Field(default_factory=list)
    conversation: list[ConversationMessage] = Field(default_factory=list)
