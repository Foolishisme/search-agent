import tempfile
import unittest
from pathlib import Path

from app.artifact_store import MarkdownArtifactStore
from app.llm_client import LLMClientError
from app.python_executor import PythonExecutionResult
from app.runtime import AgentRuntime, RunCancelledError
from app.schemas import AttachmentContext, CanvasDraft, ConversationMessage, ExecutionPlan, PythonScriptDraft, SearchDecision, SearchResult
from app.search_tool import SearchToolError


class FakeLLMClient:
    def __init__(
        self,
        *,
        plan: ExecutionPlan | None = None,
        queries: list[str] | None = None,
        decisions: list[SearchDecision] | None = None,
        final_answer_text: str = "final answer",
        canvas_draft: CanvasDraft | None = None,
        python_draft: PythonScriptDraft | None = None,
        error: Exception | None = None,
    ) -> None:
        self.plan_result = plan or ExecutionPlan(route="direct_answer", canvas_requested=False)
        self.queries = list(queries or [])
        self.decisions = list(decisions or [])
        self.final_answer_text = final_answer_text
        self.canvas_draft = canvas_draft or CanvasDraft(title="Document", content="# Document")
        self.python_draft = python_draft or PythonScriptDraft(code="print('ok')", rationale="default")
        self.error = error
        self.histories: list[list[dict]] = []
        self.conversations: list[list[ConversationMessage]] = []

    async def plan(
        self,
        question: str,
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
    ) -> ExecutionPlan:
        self.conversations.append(list(conversation or []))
        if self.error is not None:
            raise self.error
        return self.plan_result

    async def suggest_search_query(
        self,
        question: str,
        history: list[dict],
        plan: ExecutionPlan | None = None,
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
    ) -> str:
        self.histories.append([item.copy() for item in history])
        if self.error is not None:
            raise self.error
        if not self.queries:
            raise AssertionError("No more search queries configured")
        return self.queries.pop(0)

    async def assess_search_progress(
        self,
        question: str,
        history: list[dict],
        plan: ExecutionPlan | None = None,
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
    ) -> SearchDecision:
        self.histories.append([item.copy() for item in history])
        if self.error is not None:
            raise self.error
        if not self.decisions:
            raise AssertionError("No more search decisions configured")
        return self.decisions.pop(0)

    async def final_answer(
        self,
        question: str,
        history: list[dict],
        plan: ExecutionPlan | None = None,
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
    ) -> str:
        self.histories.append([item.copy() for item in history])
        if self.error is not None:
            raise self.error
        return self.final_answer_text

    async def build_canvas_document(
        self,
        question: str,
        answer: str,
        plan: ExecutionPlan | None = None,
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
    ) -> CanvasDraft:
        if self.error is not None:
            raise self.error
        return self.canvas_draft

    async def build_python_script(
        self,
        question: str,
        plan: ExecutionPlan | None = None,
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
    ) -> PythonScriptDraft:
        if self.error is not None:
            raise self.error
        return self.python_draft


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


class FakePythonExecutor:
    def __init__(self, result: PythonExecutionResult | None = None, error: Exception | None = None):
        self.result = result or PythonExecutionResult(stdout="ok\n", stderr="", exit_code=0)
        self.error = error
        self.codes: list[str] = []

    async def execute(self, code: str) -> PythonExecutionResult:
        self.codes.append(code)
        if self.error is not None:
            raise self.error
        return self.result


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.artifact_store = MarkdownArtifactStore(Path(self.tempdir.name))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    async def test_direct_answer_without_search(self):
        runtime = AgentRuntime(
            llm_client=FakeLLMClient(
                plan=ExecutionPlan(route="direct_answer", canvas_requested=False),
                final_answer_text="direct answer",
            ),
            search_tool=FakeSearchTool(),
            artifact_store=self.artifact_store,
        )

        response = await runtime.run("1+1=?")

        self.assertEqual(response.answer, "direct answer")
        self.assertFalse(response.need_search)
        self.assertIsNone(response.query)
        self.assertEqual(response.search_results, [])
        self.assertEqual([log.stage for log in response.logs], ["input", "plan", "final"])

    async def test_python_execution_then_final(self):
        python_executor = FakePythonExecutor(
            result=PythonExecutionResult(stdout="3\n", stderr="", exit_code=0)
        )
        llm_client = FakeLLMClient(
            plan=ExecutionPlan(route="python_execution", canvas_requested=False),
            python_draft=PythonScriptDraft(code="print(1 + 2)", rationale="simple math"),
            final_answer_text="The Python result is 3.",
        )
        runtime = AgentRuntime(
            llm_client=llm_client,
            search_tool=FakeSearchTool(),
            artifact_store=self.artifact_store,
            python_executor=python_executor,
        )

        response = await runtime.run("Use Python to calculate 1 + 2")

        self.assertEqual(response.answer, "The Python result is 3.")
        self.assertFalse(response.need_search)
        self.assertEqual(python_executor.codes, ["print(1 + 2)"])
        self.assertTrue(any(item.tool == "execute_python_wsl" for item in response.tool_observations))
        self.assertTrue(any(log.stage == "python" for log in response.logs))

    async def test_information_gathering_then_final(self):
        results = [SearchResult(title="Title", snippet="Snippet", url="https://example.com")]
        llm_client = FakeLLMClient(
            plan=ExecutionPlan(route="information_gathering", canvas_requested=False),
            queries=["AI Agent runtime"],
            decisions=[SearchDecision(next="answer", reason="enough")],
            final_answer_text="answer from search",
        )
        runtime = AgentRuntime(
            llm_client=llm_client,
            search_tool=FakeSearchTool(results=[results]),
            artifact_store=self.artifact_store,
        )

        response = await runtime.run("Tell me about AI Agent runtime")

        self.assertTrue(response.need_search)
        self.assertEqual(response.query, "AI Agent runtime")
        self.assertEqual(len(response.search_results), 1)
        self.assertEqual(response.answer, "answer from search")
        self.assertEqual(llm_client.histories[0], [])
        self.assertEqual(llm_client.histories[1][0]["tool"], "search_web")

    async def test_search_retry_then_answer(self):
        llm_client = FakeLLMClient(
            plan=ExecutionPlan(route="information_gathering", canvas_requested=False),
            queries=["first query"],
            decisions=[
                SearchDecision(next="retry", reason="too broad", query="second query"),
                SearchDecision(next="answer", reason="enough"),
            ],
            final_answer_text="final after retry",
        )
        runtime = AgentRuntime(
            llm_client=llm_client,
            search_tool=FakeSearchTool(
                results=[
                    [],
                    [SearchResult(title="Found", snippet="Data", url="https://example.com")],
                ]
            ),
            artifact_store=self.artifact_store,
        )

        response = await runtime.run("Need current info")

        self.assertEqual(response.answer, "final after retry")
        self.assertEqual(response.query, "second query")
        self.assertEqual(len(response.search_results), 1)

    async def test_search_retry_limit_stops_and_answers(self):
        llm_client = FakeLLMClient(
            plan=ExecutionPlan(route="information_gathering", canvas_requested=False),
            queries=["q1"],
            decisions=[
                SearchDecision(next="retry", query="q2"),
                SearchDecision(next="retry", query="q3"),
                SearchDecision(next="retry", query="q4"),
            ],
            final_answer_text="best effort answer",
        )
        runtime = AgentRuntime(
            llm_client=llm_client,
            search_tool=FakeSearchTool(results=[[], [], []]),
            artifact_store=self.artifact_store,
        )

        response = await runtime.run("hard question")

        self.assertEqual(response.answer, "best effort answer")
        self.assertTrue(any("retry limit reached" in log.message for log in response.logs))

    async def test_plan_error(self):
        runtime = AgentRuntime(
            llm_client=FakeLLMClient(error=LLMClientError("plan failed")),
            search_tool=FakeSearchTool(),
            artifact_store=self.artifact_store,
        )

        with self.assertRaises(RuntimeError) as context:
            await runtime.run("test")

        self.assertEqual(str(context.exception), "plan failed")

    async def test_search_error(self):
        runtime = AgentRuntime(
            llm_client=FakeLLMClient(
                plan=ExecutionPlan(route="information_gathering", canvas_requested=False),
                queries=["test"],
            ),
            search_tool=FakeSearchTool(error=SearchToolError("search failed")),
            artifact_store=self.artifact_store,
        )

        with self.assertRaises(RuntimeError) as context:
            await runtime.run("test")

        self.assertEqual(str(context.exception), "search failed")

    async def test_empty_question(self):
        runtime = AgentRuntime(
            llm_client=FakeLLMClient(),
            search_tool=FakeSearchTool(),
            artifact_store=self.artifact_store,
        )

        with self.assertRaises(ValueError):
            await runtime.run("   ")

    async def test_passes_conversation_memory_to_planner(self):
        llm_client = FakeLLMClient(
            plan=ExecutionPlan(route="direct_answer", canvas_requested=False),
            final_answer_text="contextual answer",
        )
        runtime = AgentRuntime(
            llm_client=llm_client,
            search_tool=FakeSearchTool(),
            artifact_store=self.artifact_store,
        )
        conversation = [
            ConversationMessage(role="user", content="We were discussing LangGraph", created_at="2026-03-24T10:00:00+08:00"),
            ConversationMessage(role="assistant", content="Yes, orchestration is key", created_at="2026-03-24T10:00:05+08:00"),
        ]

        response = await runtime.run("How is it different from AutoGen?", conversation=conversation)

        self.assertEqual(response.answer, "contextual answer")
        self.assertEqual(len(llm_client.conversations[0]), 2)

    async def test_run_stream_yields_tool_results_and_final(self):
        llm_client = FakeLLMClient(
            plan=ExecutionPlan(route="information_gathering", canvas_requested=False),
            queries=["stream test"],
            decisions=[SearchDecision(next="answer")],
            final_answer_text="stream final answer",
        )
        runtime = AgentRuntime(
            llm_client=llm_client,
            search_tool=FakeSearchTool(
                results=[[SearchResult(title="Title", snippet="Snippet", url="https://example.com")]]
            ),
            artifact_store=self.artifact_store,
        )

        events = []
        async for event in runtime.run_stream("stream test"):
            events.append(event)

        self.assertEqual(events[0]["type"], "status")
        self.assertTrue(any(item["type"] == "tool_result" for item in events))
        self.assertTrue(any(item["type"] == "results" for item in events))
        self.assertEqual(events[-1]["type"], "final_response")
        self.assertEqual(events[-1]["data"].answer, "stream final answer")

    async def test_canvas_is_postprocess_not_main_action(self):
        llm_client = FakeLLMClient(
            plan=ExecutionPlan(route="direct_answer", canvas_requested=True),
            final_answer_text="saved as markdown",
            canvas_draft=CanvasDraft(title="Guide", content="# Guide"),
        )
        runtime = AgentRuntime(
            llm_client=llm_client,
            search_tool=FakeSearchTool(),
            artifact_store=self.artifact_store,
        )

        events = []
        async for event in runtime.run_stream("Make a markdown guide", session_id="session-1"):
            events.append(event)

        self.assertTrue(any(item["type"] == "canvas" for item in events))
        self.assertEqual(events[-1]["type"], "final_response")
        artifacts = self.artifact_store.list_artifacts("session-1")
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].title, "Guide")

    async def test_run_stream_can_be_cancelled_between_search_and_final(self):
        results = [SearchResult(title="Title", snippet="Snippet", url="https://example.com")]
        cancelled = False

        class CancellableSearchTool(FakeSearchTool):
            async def search(self, query: str) -> list[SearchResult]:
                nonlocal cancelled
                payload = await super().search(query)
                cancelled = True
                return payload

        runtime = AgentRuntime(
            llm_client=FakeLLMClient(
                plan=ExecutionPlan(route="information_gathering", canvas_requested=False),
                queries=["cancel me"],
                decisions=[SearchDecision(next="answer")],
                final_answer_text="should not happen",
            ),
            search_tool=CancellableSearchTool(results=[results]),
            artifact_store=self.artifact_store,
        )

        with self.assertRaises(RunCancelledError):
            async for _ in runtime.run_stream("cancel test", is_cancelled=lambda: cancelled):
                pass
