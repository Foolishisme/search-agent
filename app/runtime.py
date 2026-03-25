import logging
from collections.abc import AsyncIterator
from typing import Any, Callable

from app.artifact_store import ArtifactStoreError
from app.artifact_tool import save_markdown_artifact
from app.llm_client import LLMClientError
from app.schemas import AskResponse, AttachmentContext, CanvasDraft, ConversationMessage, RuntimeLog, SearchDecision, SearchResult, ToolObservation
from app.search_tool import SearchToolError, TavilySearchTool

logger = logging.getLogger(__name__)


class RunCancelledError(RuntimeError):
    pass


class AgentRuntime:
    MAX_SEARCH_ATTEMPTS = 3

    def __init__(self, llm_client: Any, search_tool: TavilySearchTool, artifact_store: Any) -> None:
        self.llm_client = llm_client
        self.search_tool = search_tool
        self.artifact_store = artifact_store

    async def run(
        self,
        question: str,
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
        session_id: str | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> AskResponse:
        final_response: AskResponse | None = None
        async for event in self.run_stream(
            question,
            conversation=conversation,
            attachments=attachments,
            session_id=session_id,
            is_cancelled=is_cancelled,
        ):
            if event["type"] == "final_response":
                final_response = event["data"]
        if final_response is None:
            raise RuntimeError("Agent did not return a final response")
        return final_response

    async def run_stream(
        self,
        question: str,
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
        session_id: str | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> AsyncIterator[dict]:
        logs: list[RuntimeLog] = []
        tool_observations: list[ToolObservation] = []
        conversation = conversation or []
        attachments = attachments or []
        normalized_question = question.strip()
        latest_query: str | None = None
        last_results: list[SearchResult] = []
        latest_nonempty_results: list[SearchResult] = []

        if not normalized_question:
            raise ValueError("Question cannot be empty")

        def ensure_not_cancelled() -> None:
            if is_cancelled is not None and is_cancelled():
                raise RunCancelledError("User cancelled the current run")

        input_log = RuntimeLog(stage="input", message=f"Question: {normalized_question}")
        logs.append(input_log)
        logger.info("Received question: %s", normalized_question)
        yield {"type": "status", "message": "Analyzing request"}
        yield {"type": "log", "log": input_log}

        ensure_not_cancelled()
        plan = await self._plan_execution(normalized_question, conversation, attachments, logs)
        plan_log = RuntimeLog(
            stage="plan",
            message=f"Plan route={plan.route}, canvas_requested={plan.canvas_requested}",
        )
        logs.append(plan_log)
        yield {"type": "log", "log": plan_log}
        yield {"type": "status", "message": f"Plan selected: {plan.route}"}

        if plan.route == "information_gathering":
            next_query: str | None = None
            for attempt in range(1, self.MAX_SEARCH_ATTEMPTS + 1):
                ensure_not_cancelled()
                latest_query = next_query or await self._suggest_search_query(
                    normalized_question,
                    tool_observations,
                    conversation,
                    attachments,
                    logs,
                )
                query_log = RuntimeLog(stage="search", message=f"Search attempt {attempt}: {latest_query}")
                logs.append(query_log)
                yield {"type": "log", "log": query_log}
                yield {"type": "status", "message": f"Searching: {latest_query}"}

                results, observation, result_log = await self._execute_search(attempt, latest_query)
                logs.append(result_log)
                tool_observations.append(observation)
                yield {"type": "log", "log": result_log}
                yield {"type": "tool_result", "result": observation.model_dump(mode="json")}
                yield {"type": "results", "results": [item.model_dump(mode="json") for item in results]}

                ensure_not_cancelled()
                last_results = results
                if results:
                    latest_nonempty_results = results

                decision = await self._assess_search_progress(
                    normalized_question,
                    tool_observations,
                    conversation,
                    attachments,
                    logs,
                )
                decision_log = RuntimeLog(
                    stage="thought",
                    message=f"Search decision {attempt}: next={decision.next}" + (f", reason={decision.reason}" if decision.reason else ""),
                )
                logs.append(decision_log)
                yield {"type": "log", "log": decision_log}

                if decision.next == "retry" and attempt < self.MAX_SEARCH_ATTEMPTS:
                    next_query = (decision.query or "").strip()
                    continue

                if decision.next == "retry" and attempt >= self.MAX_SEARCH_ATTEMPTS:
                    limit_log = RuntimeLog(stage="thought", message="Search retry limit reached; answering with current evidence")
                    logs.append(limit_log)
                    yield {"type": "log", "log": limit_log}
                break

        ensure_not_cancelled()
        answer = await self._generate_final_answer(
            normalized_question,
            tool_observations,
            conversation,
            attachments,
            logs,
        )

        if plan.canvas_requested:
            canvas_payload = await self._execute_canvas_postprocess(
                question=normalized_question,
                answer=answer,
                conversation=conversation,
                attachments=attachments,
                session_id=session_id,
            )
            if canvas_payload is not None:
                canvas_log, canvas_observation, artifact = canvas_payload
                logs.append(canvas_log)
                tool_observations.append(canvas_observation)
                yield {"type": "log", "log": canvas_log}
                yield {"type": "tool_result", "result": canvas_observation.model_dump(mode="json")}
                yield {"type": "canvas", "artifact": artifact.model_dump(mode="json")}
            else:
                canvas_error_log = RuntimeLog(stage="canvas", message="Canvas post-process failed; returning answer only")
                logs.append(canvas_error_log)
                yield {"type": "log", "log": canvas_error_log}

        final_log = RuntimeLog(stage="final", message="Final answer generated")
        logs.append(final_log)
        yield {"type": "log", "log": final_log}
        yield {"type": "status", "message": "Final answer generated"}
        yield {
            "type": "final_response",
            "data": AskResponse(
                session_id="",
                session_title="",
                answer=answer,
                need_search=latest_query is not None,
                query=latest_query,
                search_results=latest_nonempty_results or last_results,
                logs=logs,
                tool_observations=tool_observations,
                conversation=[],
                attachments=[],
            ),
        }

    async def _plan_execution(
        self,
        question: str,
        conversation: list[ConversationMessage],
        attachments: list[AttachmentContext],
        logs: list[RuntimeLog],
    ):
        try:
            return await self.llm_client.plan(question, conversation=conversation, attachments=attachments)
        except LLMClientError as exc:
            error_log = RuntimeLog(stage="error", message=f"Planning failed: {exc}")
            logs.append(error_log)
            raise RuntimeError(str(exc)) from exc

    async def _suggest_search_query(
        self,
        question: str,
        tool_observations: list[ToolObservation],
        conversation: list[ConversationMessage],
        attachments: list[AttachmentContext],
        logs: list[RuntimeLog],
    ) -> str:
        try:
            return await self.llm_client.suggest_search_query(
                question,
                [item.model_dump(mode="json") for item in tool_observations],
                conversation=conversation,
                attachments=attachments,
            )
        except LLMClientError as exc:
            error_log = RuntimeLog(stage="error", message=f"Search query planning failed: {exc}")
            logs.append(error_log)
            raise RuntimeError(str(exc)) from exc

    async def _execute_search(
        self,
        step: int,
        query: str,
    ) -> tuple[list[SearchResult], ToolObservation, RuntimeLog]:
        logger.info("Search attempt %s query=%s", step, query)
        try:
            results = await self.search_tool.search(query)
        except SearchToolError as exc:
            observation = ToolObservation(
                step=step,
                tool="search",
                status="error",
                message=str(exc),
                data={"query": query},
            )
            raise RuntimeError(str(exc)) from exc

        observation = ToolObservation(
            step=step,
            tool="search",
            status="success",
            message="Search tool executed successfully",
            data={
                "query": query,
                "results_count": len(results),
                "results": [item.model_dump(mode="json") for item in results],
            },
        )
        result_log = RuntimeLog(stage="search", message=f"Search returned {len(results)} result(s)")
        return results, observation, result_log

    async def _assess_search_progress(
        self,
        question: str,
        tool_observations: list[ToolObservation],
        conversation: list[ConversationMessage],
        attachments: list[AttachmentContext],
        logs: list[RuntimeLog],
    ) -> SearchDecision:
        try:
            return await self.llm_client.assess_search_progress(
                question,
                [item.model_dump(mode="json") for item in tool_observations],
                conversation=conversation,
                attachments=attachments,
            )
        except LLMClientError as exc:
            error_log = RuntimeLog(stage="error", message=f"Search assessment failed: {exc}")
            logs.append(error_log)
            raise RuntimeError(str(exc)) from exc

    async def _generate_final_answer(
        self,
        question: str,
        tool_observations: list[ToolObservation],
        conversation: list[ConversationMessage],
        attachments: list[AttachmentContext],
        logs: list[RuntimeLog],
    ) -> str:
        try:
            return await self.llm_client.final_answer(
                question,
                [item.model_dump(mode="json") for item in tool_observations],
                conversation=conversation,
                attachments=attachments,
            )
        except LLMClientError as exc:
            error_log = RuntimeLog(stage="error", message=f"Final answer generation failed: {exc}")
            logs.append(error_log)
            raise RuntimeError(str(exc)) from exc

    async def _execute_canvas_postprocess(
        self,
        question: str,
        answer: str,
        conversation: list[ConversationMessage],
        attachments: list[AttachmentContext],
        session_id: str | None,
    ):
        if not session_id:
            raise RuntimeError("Canvas post-process requires a valid session id")

        try:
            draft: CanvasDraft = await self.llm_client.build_canvas_document(
                question,
                answer,
                conversation=conversation,
                attachments=attachments,
            )
            artifact = save_markdown_artifact(
                self.artifact_store,
                session_id=session_id,
                title=draft.title.strip(),
                content=draft.content.strip(),
            )
        except (LLMClientError, ArtifactStoreError):
            return None

        canvas_log = RuntimeLog(stage="canvas", message=f"Saved Markdown document: {artifact.title}")
        observation = ToolObservation(
            step=1000 + len(question),
            tool="canvas",
            status="success",
            message="Canvas tool saved a Markdown document",
            data={
                "title": artifact.title,
                "artifact_id": artifact.artifact_id,
                "filename": artifact.filename,
            },
        )
        return canvas_log, observation, artifact
