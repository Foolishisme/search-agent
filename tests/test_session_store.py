import tempfile
import unittest
from pathlib import Path

from app.schemas import RuntimeLog, SearchResult, ToolObservation
from app.session_store import MarkdownSessionStore


class SessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = MarkdownSessionStore(Path(self.tempdir.name))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def append_turn(self, question: str, answer: str):
        return self.store.append_turn(
            None,
            question,
            answer,
            need_search=True,
            query="示例查询",
            logs=[RuntimeLog(stage="search", message="执行了一次搜索")],
            search_results=[SearchResult(title="来源", snippet="摘要", url="https://example.com")],
            tool_observations=[
                ToolObservation(
                    step=1,
                    tool="search",
                    status="success",
                    message="搜索工具执行成功",
                    data={"query": "示例查询", "results_count": 1},
                )
            ],
        )

    def test_append_turn_persists_markdown_session(self):
        session = self.append_turn("第一条问题", "第一条回答")
        session_path = Path(self.tempdir.name) / f"{session.session_id}.md"

        self.assertTrue(session_path.exists())
        raw = session_path.read_text(encoding="utf-8")
        self.assertIn("# 第一条问题", raw)
        self.assertIn("第一条回答", raw)
        self.assertIn('"turns"', raw)

        loaded = self.store.get_session(session.session_id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(len(loaded.messages), 2)
        self.assertEqual(loaded.messages[1].content, "第一条回答")
        self.assertEqual(len(loaded.latest_logs), 1)
        self.assertEqual(loaded.latest_search_results[0].title, "来源")
        self.assertEqual(loaded.latest_tool_observations[0].tool, "search")

    def test_list_sessions_sorts_by_updated_time(self):
        first = self.append_turn("第一个问题", "第一个回答")
        second = self.append_turn("第二个问题", "第二个回答")

        sessions = self.store.list_sessions()

        self.assertEqual([item.session_id for item in sessions], [second.session_id, first.session_id])
        self.assertEqual(sessions[0].last_message_preview, "第二个回答")

    def test_delete_session_removes_markdown_file(self):
        session = self.append_turn("要删除的问题", "要删除的回答")

        deleted = self.store.delete_session(session.session_id)

        self.assertTrue(deleted)
        self.assertIsNone(self.store.get_session(session.session_id))
