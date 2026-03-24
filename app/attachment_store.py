import io
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader

from app.schemas import AttachmentContext, AttachmentMeta


class AttachmentStoreError(Exception):
    pass


class AttachmentStore:
    ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}
    INDEX_FILENAME = "index.json"

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def list_attachments(self, session_id: str) -> list[AttachmentMeta]:
        index = self._read_index(self._session_dir(session_id))
        return [AttachmentMeta.model_validate(item) for item in index]

    def list_attachment_contexts(self, session_id: str, excerpt_chars: int = 1600) -> list[AttachmentContext]:
        session_dir = self._session_dir(session_id)
        index = self._read_index(session_dir)
        contexts: list[AttachmentContext] = []
        for item in index:
            meta = AttachmentMeta.model_validate(item)
            extracted_path = session_dir / f"{meta.attachment_id}.txt"
            content = extracted_path.read_text(encoding="utf-8") if extracted_path.exists() else ""
            contexts.append(
                AttachmentContext(
                    **meta.model_dump(),
                    excerpt=content[:excerpt_chars],
                    content=content,
                )
            )
        return contexts

    def save_files(self, session_id: str, uploads: list[tuple[str, str | None, bytes]]) -> list[AttachmentMeta]:
        if not uploads:
            return self.list_attachments(session_id)

        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        index = self._read_index(session_dir)

        for filename, media_type, content in uploads:
            suffix = Path(filename or "").suffix.lower()
            if suffix not in self.ALLOWED_EXTENSIONS:
                raise AttachmentStoreError("仅支持上传 PDF、TXT、MD 文件")

            attachment_id = uuid4().hex
            safe_filename = Path(filename).name or f"attachment{suffix}"
            uploaded_at = self._now()
            original_path = session_dir / f"{attachment_id}{suffix}"
            extracted_path = session_dir / f"{attachment_id}.txt"

            original_path.write_bytes(content)
            extracted_text = self._extract_text(suffix, content)
            extracted_path.write_text(extracted_text, encoding="utf-8")

            index.append(
                AttachmentMeta(
                    attachment_id=attachment_id,
                    filename=safe_filename,
                    media_type=media_type or self._guess_media_type(suffix),
                    size_bytes=len(content),
                    uploaded_at=uploaded_at,
                ).model_dump(mode="json")
            )

        self._write_index(session_dir, index)
        return [AttachmentMeta.model_validate(item) for item in index]

    def delete_session(self, session_id: str) -> None:
        session_dir = self._session_dir(session_id)
        if not session_dir.exists():
            return
        for path in session_dir.glob("*"):
            path.unlink()
        session_dir.rmdir()

    def _session_dir(self, session_id: str) -> Path:
        return self.storage_dir / session_id

    def _read_index(self, session_dir: Path) -> list[dict]:
        index_path = session_dir / self.INDEX_FILENAME
        if not index_path.exists():
            return []
        return json.loads(index_path.read_text(encoding="utf-8"))

    def _write_index(self, session_dir: Path, index: list[dict]) -> None:
        index_path = session_dir / self.INDEX_FILENAME
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    def _extract_text(self, suffix: str, content: bytes) -> str:
        if suffix in {".txt", ".md"}:
            for encoding in ("utf-8", "utf-8-sig", "gb18030"):
                try:
                    return content.decode(encoding).strip()
                except UnicodeDecodeError:
                    continue
            raise AttachmentStoreError("文本文件编码无法识别")

        if suffix == ".pdf":
            try:
                reader = PdfReader(io.BytesIO(content))
                return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
            except Exception as exc:
                raise AttachmentStoreError("PDF 解析失败") from exc

        raise AttachmentStoreError("不支持的文件类型")

    def _guess_media_type(self, suffix: str) -> str:
        if suffix == ".pdf":
            return "application/pdf"
        if suffix == ".md":
            return "text/markdown"
        return "text/plain"

    def _now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="microseconds")
