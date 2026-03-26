import asyncio
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import app.main as app_main
from app.attachment_store import AttachmentStore
from app.artifact_store import MarkdownArtifactStore
from app.main import app
from app.runtime import RunCancelledError
from app.schemas import AskResponse, RuntimeLog, SearchResult, ToolObservation
from app.session_store import MarkdownSessionStore


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        app_main.session_store = MarkdownSessionStore(Path(self.tempdir.name))
        app_main.attachment_store = AttachmentStore(Path(self.tempdir.name) / "uploads")
        app_main.artifact_store = MarkdownArtifactStore(Path(self.tempdir.name) / "artifacts")
        app_main.runtime.artifact_store = app_main.artifact_store
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_index_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("最小搜索 Agent MVP", response.text)
        self.assertIn("cdn.jsdelivr.net/npm/marked/marked.min.js", response.text)
        self.assertIn("cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js", response.text)
        self.assertIn('id="sources"', response.text)
        self.assertIn("引用来源", response.text)
        self.assertIn('class="floating-composer"', response.text)
        self.assertIn('id="logs-panel"', response.text)
        self.assertIn('id="create-artifact"', response.text)
        self.assertIn('id="toggle-history"', response.text)
        self.assertIn('id="artifact-panel"', response.text)
        self.assertIn('id="download-artifact"', response.text)
        self.assertIn('id="sources-count-text"', response.text)
        self.assertIn(">发送问题<", response.text)
        self.assertIn("Canvas Tool", response.text)
        self.assertIn("svg-card", response.text)
        self.assertIn("copy-message", response.text)

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
            search_results=[SearchResult(title="标题", snippet="摘要", url="https://example.com")],
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
        self.assertEqual(detail["latest_logs"][0]["message"], "done")
        self.assertEqual(detail["latest_search_results"][0]["title"], "标题")
        self.assertEqual(detail["latest_tool_observations"], [])

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

    def test_api_ask_stream_with_attachment(self):
        async def fake_run_stream(*args, **kwargs):
            yield {"type": "status", "message": "正在理解问题"}
            yield {"type": "log", "log": RuntimeLog(stage="input", message="用户问题：读取附件")}
            yield {
                "type": "final_response",
                "data": AskResponse(
                    session_id="",
                    session_title="",
                    answer="附件已读取",
                    need_search=False,
                    logs=[RuntimeLog(stage="final", message="done")],
                    conversation=[],
                    attachments=[],
                ),
            }

        with patch("app.main.runtime.run_stream", new=fake_run_stream):
            response = self.client.post(
                "/api/ask/stream",
                data={"question": "读取附件"},
                files={"files": ("memo.md", b"# memo\nhello", "text/markdown")},
            )

        self.assertEqual(response.status_code, 200)
        chunks = [line for line in response.text.splitlines() if line.strip()]
        self.assertTrue(any('"type": "attachments"' in line for line in chunks))
        self.assertTrue(any('"type": "final"' in line for line in chunks))

        session_response = self.client.get("/api/sessions")
        session_id = session_response.json()[0]["session_id"]
        detail_response = self.client.get(f"/api/sessions/{session_id}")
        detail = detail_response.json()
        self.assertEqual(len(detail["attachments"]), 1)
        self.assertEqual(detail["attachments"][0]["filename"], "memo.md")

    def test_cancelled_stream_rolls_back_side_effects_and_keeps_previous_turn(self):
        first_response = AskResponse(
            session_id="",
            session_title="",
            answer="第一轮回答",
            need_search=False,
            logs=[RuntimeLog(stage="final", message="done")],
            conversation=[],
            attachments=[],
        )

        with patch("app.main.runtime.run", new=AsyncMock(return_value=first_response)):
            ask_response = self.client.post("/api/ask", json={"question": "第一轮问题"})

        session_id = ask_response.json()["session_id"]

        async def cancellable_run_stream(*args, **kwargs):
            app_main.artifact_store.create_artifact(kwargs["session_id"], "临时文档", "# 临时文档")
            while not kwargs["is_cancelled"]():
                yield {"type": "status", "message": "still running"}
                await asyncio.sleep(0.01)
            raise RunCancelledError("用户已中断当前执行")

        payload: dict[str, object] = {}

        def request_stream() -> None:
            response = self.client.post(
                "/api/ask/stream",
                data={"question": "第十轮问题", "session_id": session_id},
                files={"files": ("draft.md", b"# draft\nbody", "text/markdown")},
            )
            payload["status_code"] = response.status_code
            payload["chunks"] = [line for line in response.text.splitlines() if line.strip()]

        with patch("app.main.runtime.run_stream", new=cancellable_run_stream):
            worker = threading.Thread(target=request_stream)
            worker.start()

            run_id = None
            deadline = time.time() + 5
            while time.time() < deadline and run_id is None:
                with app_main.run_registry._lock:
                    run_id = next(iter(app_main.run_registry._runs.keys()), None)
                if run_id is None:
                    time.sleep(0.01)

            self.assertIsNotNone(run_id)
            cancel_response = self.client.post(f"/api/runs/{run_id}/cancel")
            self.assertEqual(cancel_response.status_code, 204)
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())

        self.assertEqual(payload["status_code"], 200)
        chunks = payload["chunks"]
        self.assertTrue(any('"type": "cancelled"' in line for line in chunks))
        detail_response = self.client.get(f"/api/sessions/{session_id}")
        detail = detail_response.json()
        self.assertEqual(len(detail["messages"]), 2)
        self.assertEqual(detail["messages"][0]["content"], "第一轮问题")
        self.assertEqual(detail["messages"][1]["content"], "第一轮回答")
        self.assertEqual(detail["attachments"], [])
        self.assertEqual(self.client.get(f"/api/sessions/{session_id}/artifacts").json(), [])

    def test_cancel_run_returns_404_for_unknown_run(self):
        response = self.client.post("/api/runs/missing-run/cancel")
        self.assertEqual(response.status_code, 404)

    def test_tool_observations_persist_on_session_detail(self):
        fake_response = AskResponse(
            session_id="",
            session_title="",
            answer="已完成",
            need_search=True,
            query="桥 绝句",
            logs=[RuntimeLog(stage="search", message="第 1 轮搜索返回条数：1")],
            search_results=[SearchResult(title="标题", snippet="摘要", url="https://example.com")],
            tool_observations=[
                ToolObservation(
                    step=1,
                    tool="search_web",
                    status="success",
                    message="搜索工具执行成功",
                    data={"query": "桥 绝句", "results_count": 1},
                )
            ],
            conversation=[],
            attachments=[],
        )

        with patch("app.main.runtime.run", new=AsyncMock(return_value=fake_response)):
            ask_response = self.client.post("/api/ask", json={"question": "写一首桥的绝句"})

        session_id = ask_response.json()["session_id"]
        detail_response = self.client.get(f"/api/sessions/{session_id}")
        detail = detail_response.json()
        self.assertEqual(detail["latest_tool_observations"][0]["tool"], "search_web")
        self.assertEqual(detail["latest_tool_observations"][0]["status"], "success")

    def test_artifact_endpoints(self):
        fake_response = AskResponse(
            session_id="",
            session_title="",
            answer="# 会议纪要\n\n第一条",
            need_search=False,
            logs=[RuntimeLog(stage="final", message="done")],
            conversation=[],
            attachments=[],
        )
        with patch("app.main.runtime.run", new=AsyncMock(return_value=fake_response)):
            ask_response = self.client.post("/api/ask", json={"question": "请整理一下"})

        session_id = ask_response.json()["session_id"]

        create_response = self.client.post(
            f"/api/sessions/{session_id}/artifacts/save",
            json={"title": "会议纪要", "content": "# 会议纪要\n\n第一条"},
        )
        self.assertEqual(create_response.status_code, 200)
        artifact = create_response.json()
        artifact_id = artifact["artifact_id"]

        list_response = self.client.get(f"/api/sessions/{session_id}/artifacts")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

        detail_response = self.client.get(f"/api/sessions/{session_id}/artifacts/{artifact_id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["content"], "# 会议纪要\n\n第一条")

        update_response = self.client.post(
            f"/api/sessions/{session_id}/artifacts/save",
            json={"title": "更新后的纪要", "content": "# 更新后的纪要\n\n第二条"},
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["artifact_id"], artifact_id)
        self.assertEqual(update_response.json()["title"], "更新后的纪要")

        download_response = self.client.get(f"/api/sessions/{session_id}/artifacts/{artifact_id}/download")
        self.assertEqual(download_response.status_code, 200)
        self.assertIn("attachment;", download_response.headers["content-disposition"])
        self.assertIn("更新后的纪要", download_response.text)
