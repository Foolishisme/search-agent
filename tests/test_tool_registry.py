import tempfile
import unittest
from pathlib import Path

from app.python_executor import PythonExecutionResult
from app.artifact_store import MarkdownArtifactStore
from app.schemas import SearchResult, ToolCall
from app.tool_registry import TOOL_SCHEMAS, ToolExecutionError, ToolExecutor


class FakeSearchTool:
    def __init__(self, results=None, error=None):
        self.results = list(results or [])
        self.error = error

    async def search(self, query: str):
        if self.error is not None:
            raise self.error
        if self.results:
            return self.results.pop(0)
        return []


class FakePythonExecutor:
    def __init__(self, result: PythonExecutionResult | None = None, error: Exception | None = None):
        self.result = result or PythonExecutionResult(stdout="ok\n", stderr="", exit_code=0)
        self.error = error

    async def execute(self, code: str) -> PythonExecutionResult:
        if self.error is not None:
            raise self.error
        return self.result


class ToolRegistryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.artifact_store = MarkdownArtifactStore(Path(self.tempdir.name))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_tool_schemas_expose_search_and_canvas_tools(self):
        names = [item["function"]["name"] for item in TOOL_SCHEMAS]
        self.assertIn("search_web", names)
        self.assertIn("save_markdown_artifact", names)
        self.assertIn("execute_python_wsl", names)

    async def test_search_web_tool_returns_standard_observation(self):
        executor = ToolExecutor(
            search_tool=FakeSearchTool(
                results=[[SearchResult(title="Result", snippet="Snippet", url="https://example.com")]]
            ),
            artifact_store=self.artifact_store,
        )

        outcome = await executor.call(
            ToolCall(name="search_web", arguments={"query": "agent runtime"}),
            step=1,
        )

        self.assertEqual(outcome.observation.tool, "search_web")
        self.assertEqual(outcome.observation.status, "success")
        self.assertEqual(outcome.payload["query"], "agent runtime")
        self.assertEqual(len(outcome.payload["results"]), 1)

    async def test_save_markdown_artifact_tool_returns_standard_observation(self):
        executor = ToolExecutor(
            search_tool=FakeSearchTool(),
            artifact_store=self.artifact_store,
        )

        outcome = await executor.call(
            ToolCall(
                name="save_markdown_artifact",
                arguments={
                    "session_id": "session-1",
                    "title": "Guide",
                    "content": "# Guide",
                },
            ),
            step=2,
        )

        self.assertEqual(outcome.observation.tool, "save_markdown_artifact")
        self.assertEqual(outcome.observation.status, "success")
        self.assertEqual(outcome.payload["artifact"].title, "Guide")

    async def test_execute_python_wsl_tool_returns_standard_observation(self):
        executor = ToolExecutor(
            search_tool=FakeSearchTool(),
            artifact_store=self.artifact_store,
            python_executor=FakePythonExecutor(
                result=PythonExecutionResult(stdout="3\n", stderr="", exit_code=0)
            ),
        )

        outcome = await executor.call(
            ToolCall(
                name="execute_python_wsl",
                arguments={"code": "print(1 + 2)"},
            ),
            step=3,
        )

        self.assertEqual(outcome.observation.tool, "execute_python_wsl")
        self.assertEqual(outcome.observation.status, "success")
        self.assertEqual(outcome.payload["stdout"], "3\n")
        self.assertEqual(outcome.payload["exit_code"], 0)

    async def test_search_web_tool_returns_error_observation_for_invalid_arguments(self):
        executor = ToolExecutor(
            search_tool=FakeSearchTool(),
            artifact_store=self.artifact_store,
        )

        with self.assertRaises(ToolExecutionError) as context:
            await executor.call(
                ToolCall(name="search_web", arguments={}),
                step=1,
            )

        self.assertEqual(context.exception.observation.tool, "search_web")
        self.assertEqual(context.exception.observation.status, "error")
