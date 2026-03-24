import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import app.main as app_main
from app.main import app
from app.schemas import AskResponse, RuntimeLog, SearchResult
from app.session_store import MarkdownSessionStore


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        app_main.session_store = MarkdownSessionStore(Path(self.tempdir.name))
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_index_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("最小搜索 Agent MVP", response.text)

    def test_favicon(self):
        response = self.client.get("/favicon.ico")
        self.assertEqual(response.status_code, 204)

    def test_api_ask_success_without_search(self):
        fake_response = AskResponse(
            session_id="",
            session_title="",
            answer="直接回答",
            need_search=False,
            logs=[
                RuntimeLog(stage="input", message="用户问题：1+1等于几"),
                RuntimeLog(stage="final", message="第 1 轮输出最终答案"),
            ],
            conversation=[],
        )

        with patch("app.main.runtime.run", new=AsyncMock(return_value=fake_response)) as runtime_mock:
            response = self.client.post("/api/ask", json={"question": "1+1等于几"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["answer"], "直接回答")
        self.assertFalse(payload["need_search"])
        self.assertTrue(payload["session_id"])
        runtime_mock.assert_awaited_once()

    def test_api_ask_success_with_search(self):
        fake_response = AskResponse(
            session_id="",
            session_title="",
            answer="搜索后回答",
            need_search=True,
            query="AI Agent runtime",
            search_results=[
                SearchResult(title="标题", snippet="摘要", url="https://example.com"),
            ],
            logs=[
                RuntimeLog(stage="input", message="用户问题：AI Agent runtime"),
                RuntimeLog(stage="search", message="第 1 轮搜索返回条数：1"),
                RuntimeLog(stage="final", message="第 2 轮输出最终答案"),
            ],
            conversation=[],
        )

        with patch("app.main.runtime.run", new=AsyncMock(return_value=fake_response)):
            response = self.client.post("/api/ask", json={"question": "AI Agent runtime"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["need_search"])
        self.assertEqual(payload["query"], "AI Agent runtime")
        self.assertEqual(len(payload["search_results"]), 1)

    def test_api_ask_empty_question_validation(self):
        response = self.client.post("/api/ask", json={"question": ""})
        self.assertEqual(response.status_code, 422)

    def test_api_ask_runtime_error(self):
        with patch("app.main.runtime.run", new=AsyncMock(side_effect=RuntimeError("测试异常"))):
            response = self.client.post("/api/ask", json={"question": "test"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "测试异常")

    def test_sessions_endpoints(self):
        fake_response = AskResponse(
            session_id="",
            session_title="",
            answer="第一轮回答",
            need_search=False,
            logs=[RuntimeLog(stage="final", message="done")],
            conversation=[],
        )

        with patch("app.main.runtime.run", new=AsyncMock(return_value=fake_response)):
            ask_response = self.client.post("/api/ask", json={"question": "第一轮问题"})

        self.assertEqual(ask_response.status_code, 200)
        session_id = ask_response.json()["session_id"]

        list_response = self.client.get("/api/sessions")
        self.assertEqual(list_response.status_code, 200)
        sessions = list_response.json()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], session_id)

        detail_response = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(len(detail["messages"]), 2)
        self.assertEqual(detail["messages"][0]["content"], "第一轮问题")

        delete_response = self.client.delete(f"/api/sessions/{session_id}")
        self.assertEqual(delete_response.status_code, 204)
        self.assertEqual(self.client.get("/api/sessions").json(), [])

    def test_continue_existing_session_passes_history_to_runtime(self):
        first_response = AskResponse(
            session_id="",
            session_title="",
            answer="第一轮回答",
            need_search=False,
            logs=[RuntimeLog(stage="final", message="done")],
            conversation=[],
        )
        second_response = AskResponse(
            session_id="",
            session_title="",
            answer="第二轮回答",
            need_search=False,
            logs=[RuntimeLog(stage="final", message="done")],
            conversation=[],
        )

        with patch("app.main.runtime.run", new=AsyncMock(side_effect=[first_response, second_response])) as runtime_mock:
            first = self.client.post("/api/ask", json={"question": "第一轮问题"})
            session_id = first.json()["session_id"]
            second = self.client.post("/api/ask", json={"question": "继续追问", "session_id": session_id})

        self.assertEqual(second.status_code, 200)
        continuation_call = runtime_mock.await_args_list[1]
        self.assertEqual(len(continuation_call.kwargs["conversation"]), 2)
        self.assertEqual(continuation_call.kwargs["conversation"][0].content, "第一轮问题")
