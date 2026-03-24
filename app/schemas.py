from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1)


class SearchResult(BaseModel):
    title: str
    snippet: str
    url: str


class DecisionResult(BaseModel):
    need_search: bool
    query: str | None = None
    answer: str | None = None


class RuntimeLog(BaseModel):
    stage: Literal["input", "decision", "search", "final", "error"]
    message: str


class AskResponse(BaseModel):
    answer: str
    need_search: bool
    query: str | None = None
    search_results: list[SearchResult] = Field(default_factory=list)
    logs: list[RuntimeLog] = Field(default_factory=list)
