import tempfile
import unittest
from pathlib import Path

from app.artifact_store import MarkdownArtifactStore
from app.artifact_tool import save_markdown_artifact


class ArtifactToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = MarkdownArtifactStore(Path(self.tempdir.name))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_save_markdown_artifact_upserts_latest_document(self):
        created = save_markdown_artifact(
            self.store,
            session_id="session-1",
            title="文档一",
            content="# 文档一\n\n内容一",
        )
        updated = save_markdown_artifact(
            self.store,
            session_id="session-1",
            title="文档一-更新",
            content="# 文档一-更新\n\n内容二",
        )

        self.assertEqual(created.artifact_id, updated.artifact_id)
        self.assertEqual(updated.title, "文档一-更新")
