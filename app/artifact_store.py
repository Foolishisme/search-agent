import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.schemas import ArtifactDetail, ArtifactSummary


class ArtifactStoreError(Exception):
    pass


class MarkdownArtifactStore:
    INDEX_FILENAME = "index.json"

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def list_artifacts(self, session_id: str) -> list[ArtifactSummary]:
        session_dir = self._session_dir(session_id)
        index = self._read_index(session_dir)
        artifacts = [ArtifactSummary.model_validate(item) for item in index]
        artifacts.sort(key=lambda item: item.updated_at, reverse=True)
        return artifacts

    def create_artifact(self, session_id: str, title: str, content: str) -> ArtifactDetail:
        normalized_title = title.strip()
        normalized_content = content.strip()
        if not normalized_title:
            raise ArtifactStoreError("文档标题不能为空")
        if not normalized_content:
            raise ArtifactStoreError("文档内容不能为空")

        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        index = self._read_index(session_dir)
        now = self._now()
        artifact_id = uuid4().hex
        filename = self._build_filename(normalized_title, artifact_id)
        detail = ArtifactDetail(
            artifact_id=artifact_id,
            session_id=session_id,
            title=normalized_title,
            filename=filename,
            created_at=now,
            updated_at=now,
            content=normalized_content,
        )
        (session_dir / filename).write_text(normalized_content, encoding="utf-8")
        index.append(
            ArtifactSummary(
                artifact_id=artifact_id,
                session_id=session_id,
                title=normalized_title,
                filename=filename,
                created_at=now,
                updated_at=now,
            ).model_dump(mode="json")
        )
        self._write_index(session_dir, index)
        return detail

    def get_artifact(self, session_id: str, artifact_id: str) -> ArtifactDetail | None:
        session_dir = self._session_dir(session_id)
        index = self._read_index(session_dir)
        for item in index:
            summary = ArtifactSummary.model_validate(item)
            if summary.artifact_id == artifact_id:
                content = (session_dir / summary.filename).read_text(encoding="utf-8")
                return ArtifactDetail(**summary.model_dump(), content=content)
        return None

    def update_artifact(self, session_id: str, artifact_id: str, title: str, content: str) -> ArtifactDetail:
        normalized_title = title.strip()
        normalized_content = content.strip()
        if not normalized_title:
            raise ArtifactStoreError("文档标题不能为空")
        if not normalized_content:
            raise ArtifactStoreError("文档内容不能为空")

        session_dir = self._session_dir(session_id)
        index = self._read_index(session_dir)
        for idx, item in enumerate(index):
            summary = ArtifactSummary.model_validate(item)
            if summary.artifact_id != artifact_id:
                continue

            now = self._now()
            old_path = session_dir / summary.filename
            filename = summary.filename
            if summary.title != normalized_title:
                filename = self._build_filename(normalized_title, artifact_id)
                new_path = session_dir / filename
                if old_path.exists() and old_path != new_path:
                    old_path.rename(new_path)
                old_path = new_path

            old_path.write_text(normalized_content, encoding="utf-8")
            updated_summary = ArtifactSummary(
                artifact_id=artifact_id,
                session_id=session_id,
                title=normalized_title,
                filename=filename,
                created_at=summary.created_at,
                updated_at=now,
            )
            index[idx] = updated_summary.model_dump(mode="json")
            self._write_index(session_dir, index)
            return ArtifactDetail(**updated_summary.model_dump(), content=normalized_content)

        raise ArtifactStoreError("文档不存在")

    def get_artifact_path(self, session_id: str, artifact_id: str) -> Path | None:
        detail = self.get_artifact(session_id, artifact_id)
        if detail is None:
            return None
        return self._session_dir(session_id) / detail.filename

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
        (session_dir / self.INDEX_FILENAME).write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_filename(self, title: str, artifact_id: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff_-]+", "-", title).strip("-").lower()
        safe_slug = slug[:40] or "document"
        return f"{safe_slug}-{artifact_id[:8]}.md"

    def _now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="microseconds")
