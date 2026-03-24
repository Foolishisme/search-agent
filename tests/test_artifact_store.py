import tempfile
import unittest
from pathlib import Path

from app.artifact_store import ArtifactStoreError, MarkdownArtifactStore


class ArtifactStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = MarkdownArtifactStore(Path(self.tempdir.name))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_create_and_load_artifact(self):
        created = self.store.create_artifact("session-1", "示例文档", "# 标题\n\n正文")

        self.assertTrue((Path(self.tempdir.name) / "session-1" / created.filename).exists())
        loaded = self.store.get_artifact("session-1", created.artifact_id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.content, "# 标题\n\n正文")

    def test_update_artifact(self):
        created = self.store.create_artifact("session-1", "示例文档", "旧内容")

        updated = self.store.update_artifact("session-1", created.artifact_id, "新标题", "新内容")

        self.assertEqual(updated.title, "新标题")
        self.assertEqual(updated.content, "新内容")
        self.assertIn("新标题".lower().replace(" ", "-"), updated.filename)

    def test_rejects_empty_content(self):
        with self.assertRaises(ArtifactStoreError):
            self.store.create_artifact("session-1", "示例文档", "   ")

    def test_save_artifact_creates_then_updates_latest(self):
        created = self.store.save_artifact("session-1", "第一次标题", "第一次内容")
        updated = self.store.save_artifact("session-1", "第二次标题", "第二次内容")

        self.assertEqual(created.artifact_id, updated.artifact_id)
        self.assertEqual(updated.title, "第二次标题")
        self.assertEqual(updated.content, "第二次内容")
