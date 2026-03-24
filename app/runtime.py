import logging

from typing import Any

from app.llm_client import LLMClientError
from app.schemas import AskResponse, ConversationMessage, RuntimeLog
from app.search_tool import SearchToolError, TavilySearchTool

logger = logging.getLogger(__name__)


class AgentRuntime:
    MAX_STEPS = 4

    def __init__(self, llm_client: Any, search_tool: TavilySearchTool) -> None:
        self.llm_client = llm_client
        self.search_tool = search_tool

    async def run(self, question: str, conversation: list[ConversationMessage] | None = None) -> AskResponse:
        logs: list[RuntimeLog] = []
        history: list[dict] = []
        aggregated_results = []
        latest_query: str | None = None
        conversation = conversation or []
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("问题不能为空")

        logs.append(RuntimeLog(stage="input", message=f"用户问题：{normalized_question}"))
        logger.info("收到用户问题: %s", normalized_question)

        for step in range(1, self.MAX_STEPS + 1):
            try:
                action = await self.llm_client.next_action(normalized_question, history, conversation)
            except LLMClientError as exc:
                logs.append(RuntimeLog(stage="error", message=f"第 {step} 轮决策失败：{exc}"))
                raise RuntimeError(str(exc)) from exc

            logs.append(RuntimeLog(stage="thought", message=f"第 {step} 轮 action：{action.action}"))
            logger.info("第 %s 轮 action=%s", step, action.action)

            if action.action == "final":
                answer = (action.answer or "").strip()
                logs.append(RuntimeLog(stage="final", message=f"第 {step} 轮输出最终答案"))
                logger.info("第 %s 轮完成 final", step)
                return AskResponse(
                    session_id="",
                    session_title="",
                    answer=answer,
                    need_search=latest_query is not None,
                    query=latest_query,
                    search_results=aggregated_results,
                    logs=logs,
                    conversation=[],
                )

            query = (action.query or "").strip()
            latest_query = query
            logs.append(RuntimeLog(stage="search", message=f"第 {step} 轮搜索词：{query}"))
            logger.info("第 %s 轮开始搜索 query=%s", step, query)

            try:
                results = await self.search_tool.search(query)
            except SearchToolError as exc:
                logs.append(RuntimeLog(stage="error", message=f"第 {step} 轮搜索失败：{exc}"))
                raise RuntimeError(str(exc)) from exc

            aggregated_results = results
            history.append(
                {
                    "step": step,
                    "action": "search",
                    "query": query,
                    "results": [item.model_dump() for item in results],
                }
            )
            logs.append(RuntimeLog(stage="search", message=f"第 {step} 轮搜索返回条数：{len(results)}"))
            logger.info("第 %s 轮搜索完成 count=%s", step, len(results))

            if not results:
                logs.append(RuntimeLog(stage="thought", message=f"第 {step} 轮搜索无结果，继续交给 LLM 决策"))

        logs.append(RuntimeLog(stage="error", message="达到最大循环步数，强制结束"))
        raise RuntimeError("Agent 达到最大执行步数，未能在限制内完成")
