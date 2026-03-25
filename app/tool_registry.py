from dataclasses import dataclass
from typing import Any

from app.artifact_store import ArtifactStoreError, MarkdownArtifactStore
from app.artifact_tool import SAVE_MARKDOWN_ARTIFACT_TOOL, save_markdown_artifact
from app.schemas import ToolCall, ToolObservation
from app.search_tool import SearchToolError, TavilySearchTool

SEARCH_WEB_TOOL = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Search the public web for up-to-date information and return normalized search results.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The web search query to execute.",
                },
            },
            "required": ["query"],
        },
    },
}

TOOL_SCHEMAS = [
    SEARCH_WEB_TOOL,
    SAVE_MARKDOWN_ARTIFACT_TOOL,
]


@dataclass
class ToolExecutionOutcome:
    observation: ToolObservation
    payload: dict[str, Any]


class ToolExecutionError(RuntimeError):
    def __init__(self, observation: ToolObservation) -> None:
        super().__init__(observation.message)
        self.observation = observation


class ToolExecutor:
    def __init__(self, search_tool: TavilySearchTool, artifact_store: MarkdownArtifactStore) -> None:
        self.search_tool = search_tool
        self.artifact_store = artifact_store

    @property
    def tool_schemas(self) -> list[dict[str, Any]]:
        return TOOL_SCHEMAS

    async def call(self, call: ToolCall, *, step: int) -> ToolExecutionOutcome:
        if call.name == "search_web":
            return await self._search_web(call, step=step)

        if call.name == "save_markdown_artifact":
            return self._save_markdown_artifact(call, step=step)

        observation = ToolObservation(
            step=step,
            tool=call.name,
            status="error",
            message=f"Unsupported tool: {call.name}",
            data={"arguments": call.arguments},
        )
        raise ToolExecutionError(observation)

    async def _search_web(self, call: ToolCall, *, step: int) -> ToolExecutionOutcome:
        query = str(call.arguments.get("query", "")).strip()
        if not query:
            observation = ToolObservation(
                step=step,
                tool="search_web",
                status="error",
                message="Search query cannot be empty",
                data={"arguments": call.arguments},
            )
            raise ToolExecutionError(observation)

        try:
            results = await self.search_tool.search(query)
        except SearchToolError as exc:
            observation = ToolObservation(
                step=step,
                tool="search_web",
                status="error",
                message=str(exc),
                data={"query": query},
            )
            raise ToolExecutionError(observation) from exc

        observation = ToolObservation(
            step=step,
            tool="search_web",
            status="success",
            message="Search tool executed successfully",
            data={
                "query": query,
                "results_count": len(results),
                "results": [item.model_dump(mode="json") for item in results],
            },
        )
        return ToolExecutionOutcome(
            observation=observation,
            payload={
                "query": query,
                "results": results,
            },
        )

    def _save_markdown_artifact(self, call: ToolCall, *, step: int) -> ToolExecutionOutcome:
        session_id = str(call.arguments.get("session_id", "")).strip()
        title = str(call.arguments.get("title", "")).strip()
        content = str(call.arguments.get("content", "")).strip()
        artifact_id = call.arguments.get("artifact_id")

        if not session_id:
            observation = ToolObservation(
                step=step,
                tool="save_markdown_artifact",
                status="error",
                message="Canvas tool requires a valid session id",
                data={"arguments": call.arguments},
            )
            raise ToolExecutionError(observation)

        try:
            artifact = save_markdown_artifact(
                self.artifact_store,
                session_id=session_id,
                title=title,
                content=content,
                artifact_id=artifact_id,
            )
        except ArtifactStoreError as exc:
            observation = ToolObservation(
                step=step,
                tool="save_markdown_artifact",
                status="error",
                message=str(exc),
                data={
                    "session_id": session_id,
                    "title": title,
                },
            )
            raise ToolExecutionError(observation) from exc

        observation = ToolObservation(
            step=step,
            tool="save_markdown_artifact",
            status="success",
            message="Canvas tool saved a Markdown document",
            data={
                "title": artifact.title,
                "artifact_id": artifact.artifact_id,
                "filename": artifact.filename,
            },
        )
        return ToolExecutionOutcome(
            observation=observation,
            payload={"artifact": artifact},
        )
