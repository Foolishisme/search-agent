import logging

from collections.abc import AsyncIterator
from typing import Any

from app.artifact_store import ArtifactStoreError
from app.artifact_tool import save_markdown_artifact
from app.llm_client import LLMClientError
from app.schemas import AskResponse, AttachmentContext, ConversationMessage, RuntimeLog, ToolObservation
from app.search_tool import SearchToolError, TavilySearchTool

logger = logging.getLogger(__name__)


class AgentRuntime:
    MAX_STEPS = 4

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
    ) -> AskResponse:
        final_response: AskResponse | None = None
        async for event in self.run_stream(
            question,
            conversation=conversation,
            attachments=attachments,
            session_id=session_id,
        ):
            if event["type"] == "final_response":
                final_response = event["data"]
        if final_response is None:
            raise RuntimeError("Agent 未返回最终结果")
        return final_response

    async def run_stream(
        self,
        question: str,
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
        session_id: str | None = None,
    ) -> AsyncIterator[dict]:
        logs: list[RuntimeLog] = []
        tool_observations: list[ToolObservation] = []
        aggregated_results = []
        latest_query: str | None = None
        conversation = conversation or []
        attachments = attachments or []
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("问题不能为空")

        input_log = RuntimeLog(stage="input", message=f"用户问题：{normalized_question}")
        logs.append(input_log)
        logger.info("收到用户问题: %s", normalized_question)
        yield {"type": "status", "message": "正在理解问题"}
        yield {"type": "log", "log": input_log}

        for step in range(1, self.MAX_STEPS + 1):
            try:
                action = await self.llm_client.next_action(
                    normalized_question,
                    [item.model_dump(mode="json") for item in tool_observations],
                    conversation,
                    attachments,
                )
            except LLMClientError as exc:
                error_log = RuntimeLog(stage="error", message=f"第 {step} 轮决策失败：{exc}")
                logs.append(error_log)
                yield {"type": "log", "log": error_log}
                raise RuntimeError(str(exc)) from exc

            thought_log = RuntimeLog(stage="thought", message=f"第 {step} 轮 action：{action.action}")
            logs.append(thought_log)
            logger.info("第 %s 轮 action=%s", step, action.action)
            yield {"type": "status", "message": f"第 {step} 轮决策：{action.action}"}
            yield {"type": "log", "log": thought_log}

            if action.action == "final":
                answer = (action.answer or "").strip()
                final_log = RuntimeLog(stage="final", message=f"第 {step} 轮输出最终答案")
                logs.append(final_log)
                logger.info("第 %s 轮完成 final", step)
                yield {"type": "log", "log": final_log}
                yield {"type": "status", "message": "已生成最终答案"}
                yield {
                    "type": "final_response",
                    "data": AskResponse(
                        session_id="",
                        session_title="",
                        answer=answer,
                        need_search=latest_query is not None,
                        query=latest_query,
                        search_results=aggregated_results,
                        logs=logs,
                        tool_observations=tool_observations,
                        conversation=[],
                        attachments=[],
                    ),
                }
                return

            if action.action == "canvas":
                if not session_id:
                    raise RuntimeError("Canvas 工具需要有效的会话 ID")
                try:
                    artifact = save_markdown_artifact(
                        self.artifact_store,
                        session_id=session_id,
                        title=(action.title or "").strip(),
                        content=(action.content or "").strip(),
                    )
                except ArtifactStoreError as exc:
                    error_log = RuntimeLog(stage="error", message=f"第 {step} 轮 Canvas 执行失败：{exc}")
                    logs.append(error_log)
                    error_observation = ToolObservation(
                        step=step,
                        tool="canvas",
                        status="error",
                        message=str(exc),
                        data={"title": (action.title or "").strip()},
                    )
                    tool_observations.append(error_observation)
                    yield {"type": "log", "log": error_log}
                    yield {"type": "tool_result", "result": error_observation.model_dump(mode="json")}
                    raise RuntimeError(str(exc)) from exc
                canvas_log = RuntimeLog(stage="canvas", message=f"第 {step} 轮已保存 Markdown 文档：{artifact.title}")
                logs.append(canvas_log)
                observation = ToolObservation(
                    step=step,
                    tool="canvas",
                    status="success",
                    message="Canvas 工具已成功保存 Markdown 文档",
                    data={
                        "title": artifact.title,
                        "artifact_id": artifact.artifact_id,
                        "filename": artifact.filename,
                    },
                )
                tool_observations.append(observation)
                yield {"type": "log", "log": canvas_log}
                yield {"type": "tool_result", "result": observation.model_dump(mode="json")}
                yield {"type": "status", "message": f"已使用 Canvas 工具保存文档：{artifact.title}"}
                yield {"type": "canvas", "artifact": artifact.model_dump(mode="json")}
                continue

            query = (action.query or "").strip()
            latest_query = query
            search_log = RuntimeLog(stage="search", message=f"第 {step} 轮搜索词：{query}")
            logs.append(search_log)
            logger.info("第 %s 轮开始搜索 query=%s", step, query)
            yield {"type": "status", "message": f"正在搜索：{query}"}
            yield {"type": "log", "log": search_log}

            try:
                results = await self.search_tool.search(query)
            except SearchToolError as exc:
                error_log = RuntimeLog(stage="error", message=f"第 {step} 轮搜索失败：{exc}")
                logs.append(error_log)
                error_observation = ToolObservation(
                    step=step,
                    tool="search",
                    status="error",
                    message=str(exc),
                    data={"query": query},
                )
                tool_observations.append(error_observation)
                yield {"type": "log", "log": error_log}
                yield {"type": "tool_result", "result": error_observation.model_dump(mode="json")}
                raise RuntimeError(str(exc)) from exc

            aggregated_results = results
            observation = ToolObservation(
                step=step,
                tool="search",
                status="success",
                message="搜索工具执行成功",
                data={
                    "query": query,
                    "results_count": len(results),
                    "results": [item.model_dump(mode="json") for item in results],
                },
            )
            tool_observations.append(observation)
            result_log = RuntimeLog(stage="search", message=f"第 {step} 轮搜索返回条数：{len(results)}")
            logs.append(result_log)
            logger.info("第 %s 轮搜索完成 count=%s", step, len(results))
            yield {"type": "log", "log": result_log}
            yield {"type": "tool_result", "result": observation.model_dump(mode="json")}
            yield {"type": "results", "results": [item.model_dump(mode='json') for item in results]}

            if not results:
                empty_log = RuntimeLog(stage="thought", message=f"第 {step} 轮搜索无结果，继续交给 LLM 决策")
                logs.append(empty_log)
                yield {"type": "log", "log": empty_log}

        error_log = RuntimeLog(stage="error", message="达到最大循环步数，强制结束")
        logs.append(error_log)
        yield {"type": "log", "log": error_log}
        raise RuntimeError("Agent 达到最大执行步数，未能在限制内完成")
