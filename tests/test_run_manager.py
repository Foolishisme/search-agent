import tempfile
import unittest
from pathlib import Path

from app.attachment_store import AttachmentStore
from app.artifact_store import MarkdownArtifactStore
from app.run_manager import RunRegistry, SessionStateGuard
from app.session_store import MarkdownSessionStore


class RunManagerTests(unittest.TestCase):
    def test_run_registry_create_cancel_remove(self):
        registry = RunRegistry()
        run_id = registry.create()

        self.assertFalse(registry.is_cancelled(run_id))
        self.assertTrue(registry.cancel(run_id))
        self.assertTrue(registry.is_cancelled(run_id))
        registry.remove(run_id)
        self.assertFalse(registry.is_cancelled(run_id))
        self.assertFalse(registry.cancel(run_id))

    def test_state_guard_rolls_back_attachments_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            session_store = MarkdownSessionStore(base / "sessions")
            attachment_store = AttachmentStore(base / "uploads")
            artifact_store = MarkdownArtifactStore(base / "artifacts")
            session_id = "session-1"

            attachment_store.save_files(session_id, [("a.md", "text/markdown", b"# a\nseed")])
            artifact_store.create_artifact(session_id, "Seed", "# seed")

            before_attachments = attachment_store.list_attachments(session_id)
            before_artifacts = artifact_store.list_artifacts(session_id)

            guard = SessionStateGuard(session_id, session_store, attachment_store, artifact_store)
            guard.begin()

            attachment_store.save_files(session_id, [("b.md", "text/markdown", b"# b\nnew")])
            artifact_store.save_artifact(session_id, "Changed", "# changed")

            guard.rollback()

            self.assertEqual(
                [item.filename for item in attachment_store.list_attachments(session_id)],
                [item.filename for item in before_attachments],
            )
            restored_artifacts = artifact_store.list_artifacts(session_id)
            self.assertEqual(len(restored_artifacts), len(before_artifacts))
            self.assertEqual(restored_artifacts[0].title, before_artifacts[0].title)
