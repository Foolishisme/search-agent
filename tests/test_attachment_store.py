import tempfile
import unittest
from pathlib import Path

from app.attachment_store import AttachmentStore, AttachmentStoreError


class AttachmentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = AttachmentStore(Path(self.tempdir.name))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_save_and_list_text_attachment(self):
        attachments = self.store.save_files(
            "session-1",
            [("notes.md", "text/markdown", b"# title\n\nhello world")],
        )

        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].filename, "notes.md")

        contexts = self.store.list_attachment_contexts("session-1")
        self.assertEqual(contexts[0].content, "# title\n\nhello world")
        self.assertIn("hello world", contexts[0].excerpt)

    def test_rejects_unsupported_extension(self):
        with self.assertRaises(AttachmentStoreError):
            self.store.save_files("session-1", [("image.png", "image/png", b"123")])
