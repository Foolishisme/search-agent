import unittest

from app.llm_client import LLMClientError
from app.runtime import AgentRuntime
from app.schemas import AgentAction, ConversationMessage, SearchResult
from app.search_tool import SearchToolError


class FakeLLMClient:
    def __init__(self, actions=None, error=None):
        self.actions = list(actions or [])
        self.error = error
        self.histories = []
        self.conversations = []

    async def next_action(
        self,
        question: str,
        history: list[dict],
        conversation: list[ConversationMessage] | None = None,
    ) -> AgentAction:
        self.histories.append([item.copy() for item in history])
        self.conversations.append(list(conversation or []))
        if self.error is not None:
            raise self.error
        if not self.actions:
            raise AssertionError("No more fake actions configured")
        return self.actions.pop(0)


class FakeSearchTool:
    def __init__(self, results=None, error=None):
        self.results = list(results or [])
        self.error = error
        self.queries = []

    async def search(self, query: str) -> list[SearchResult]:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        if self.results:
            return self.results.pop(0)
        return []


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_final_without_search(self):
        runtime = AgentRuntime(
            llm_client=FakeLLMClient(actions=[AgentAction(action="final", answer="直接答案")]),
            search_tool=FakeSearchTool(),
        )

        response = await runtime.run("1+1等于几")

        self.assertEqual(response.answer, "直接答案")
        self.assertFalse(response.need_search)
        self.assertIsNone(response.query)
        self.assertEqual(response.search_results, [])
        self.assertEqual([log.stage for log in response.logs], ["input", "thought", "final"])

    async def test_search_then_final(self):
        results = [
            SearchResult(title="标题", snippet="摘要", url="https://example.com"),
        ]
        llm_client = FakeLLMClient(
            actions=[
                AgentAction(action="search", query="AI Agent runtime"),
                AgentAction(action="final", answer="基于搜索结果的最终答案"),
            ]
        )
        search_tool = FakeSearchTool(results=[results])
        runtime = AgentRuntime(llm_client=llm_client, search_tool=search_tool)

        response = await runtime.run("帮我查一下 AI Agent runtime")

        self.assertTrue(response.need_search)
        self.assertEqual(response.query, "AI Agent runtime")
        self.assertEqual(len(response.search_results), 1)
        self.assertEqual(response.answer, "基于搜索结果的最终答案")
        self.assertEqual(search_tool.queries, ["AI Agent runtime"])
        self.assertEqual(llm_client.histories[0], [])
        self.assertEqual(llm_client.histories[1][0]["query"], "AI Agent runtime")
        self.assertEqual(llm_client.histories[1][0]["results"][0]["title"], "标题")
        self.assertEqual(llm_client.conversations[0], [])

    async def test_search_empty_results_then_final(self):
        llm_client = FakeLLMClient(
            actions=[
                AgentAction(action="search", query="冷门主题"),
                AgentAction(action="final", answer="未找到充分信息，暂时无法确认。"),
            ]
        )
        runtime = AgentRuntime(llm_client=llm_client, search_tool=FakeSearchTool(results=[[]]))

        response = await runtime.run("请查一个很冷门的问题")

        self.assertTrue(response.need_search)
        self.assertEqual(response.query, "冷门主题")
        self.assertEqual(response.search_results, [])
        self.assertIn("未找到充分信息", response.answer)
        self.assertTrue(any("搜索无结果" in log.message for log in response.logs))

    async def test_max_steps_guard(self):
        runtime = AgentRuntime(
            llm_client=FakeLLMClient(
                actions=[
                    AgentAction(action="search", query="q1"),
                    AgentAction(action="search", query="q2"),
                    AgentAction(action="search", query="q3"),
                    AgentAction(action="search", query="q4"),
                ]
            ),
            search_tool=FakeSearchTool(results=[[], [], [], []]),
        )

        with self.assertRaises(RuntimeError) as context:
            await runtime.run("循环问题")

        self.assertIn("最大执行步数", str(context.exception))

    async def test_llm_error(self):
        runtime = AgentRuntime(
            llm_client=FakeLLMClient(error=LLMClientError("LLM 异常")),
            search_tool=FakeSearchTool(),
        )

        with self.assertRaises(RuntimeError) as context:
            await runtime.run("测试")

        self.assertEqual(str(context.exception), "LLM 异常")

    async def test_search_error(self):
        runtime = AgentRuntime(
            llm_client=FakeLLMClient(actions=[AgentAction(action="search", query="test")]),
            search_tool=FakeSearchTool(error=SearchToolError("搜索异常")),
        )

        with self.assertRaises(RuntimeError) as context:
            await runtime.run("测试")

        self.assertEqual(str(context.exception), "搜索异常")

    async def test_empty_question(self):
        runtime = AgentRuntime(
            llm_client=FakeLLMClient(actions=[AgentAction(action="final", answer="ignored")]),
            search_tool=FakeSearchTool(),
        )

        with self.assertRaises(ValueError) as context:
            await runtime.run("   ")

        self.assertEqual(str(context.exception), "问题不能为空")

    async def test_passes_conversation_memory_to_llm(self):
        llm_client = FakeLLMClient(actions=[AgentAction(action="final", answer="结合上下文的答案")])
        runtime = AgentRuntime(
            llm_client=llm_client,
            search_tool=FakeSearchTool(),
        )
        conversation = [
            ConversationMessage(role="user", content="我们刚才在聊 LangGraph", created_at="2026-03-24T10:00:00+08:00"),
            ConversationMessage(role="assistant", content="是的，重点在编排", created_at="2026-03-24T10:00:05+08:00"),
        ]

        response = await runtime.run("它和 AutoGen 有什么差别？", conversation=conversation)

        self.assertEqual(response.answer, "结合上下文的答案")
        self.assertEqual(len(llm_client.conversations[0]), 2)
        self.assertEqual(llm_client.conversations[0][0].content, "我们刚才在聊 LangGraph")
