import logging

from app.llm_client import GeminiClient, LLMClientError
from app.schemas import AskResponse, RuntimeLog
from app.search_tool import SearchToolError, TavilySearchTool

logger = logging.getLogger(__name__)


class AgentRuntime:
    def __init__(self, llm_client: GeminiClient, search_tool: TavilySearchTool) -> None:
        self.llm_client = llm_client
        self.search_tool = search_tool

    async def run(self, question: str) -> AskResponse:
        logs: list[RuntimeLog] = []
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("问题不能为空")

        logs.append(RuntimeLog(stage="input", message=f"用户问题：{normalized_question}"))
        logger.info("收到用户问题: %s", normalized_question)

        try:
            decision = await self.llm_client.decide(normalized_question)
        except LLMClientError as exc:
            logs.append(RuntimeLog(stage="error", message=f"决策阶段失败：{exc}"))
            raise RuntimeError(str(exc)) from exc

        logs.append(RuntimeLog(stage="decision", message=f"是否触发搜索：{decision.need_search}"))
        logger.info("LLM 决策 need_search=%s", decision.need_search)

        if not decision.need_search:
            answer = (decision.answer or "").strip()
            logs.append(RuntimeLog(stage="final", message="直接回答完成"))
            logger.info("直接回答完成")
            return AskResponse(answer=answer, need_search=False, logs=logs)

        query = (decision.query or "").strip()
        logs.append(RuntimeLog(stage="search", message=f"搜索词：{query}"))
        logger.info("开始搜索 query=%s", query)

        try:
            results = await self.search_tool.search(query)
        except SearchToolError as exc:
            logs.append(RuntimeLog(stage="error", message=f"搜索阶段失败：{exc}"))
            raise RuntimeError(str(exc)) from exc

        logs.append(RuntimeLog(stage="search", message=f"搜索返回条数：{len(results)}"))
        logger.info("搜索完成 count=%s", len(results))

        if not results:
            answer = "未找到充分搜索结果，当前无法给出可靠答案。"
            logs.append(RuntimeLog(stage="final", message="搜索无结果，返回友好提示"))
            return AskResponse(
                answer=answer,
                need_search=True,
                query=query,
                search_results=[],
                logs=logs,
            )

        try:
            answer = await self.llm_client.summarize(normalized_question, results)
        except LLMClientError as exc:
            logs.append(RuntimeLog(stage="error", message=f"总结阶段失败：{exc}"))
            raise RuntimeError(str(exc)) from exc

        logs.append(RuntimeLog(stage="final", message="最终答案生成完成"))
        logger.info("最终答案生成完成")
        return AskResponse(
            answer=answer,
            need_search=True,
            query=query,
            search_results=results,
            logs=logs,
        )
