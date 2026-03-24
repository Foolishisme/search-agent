import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.schemas import ConversationMessage, SessionDetail, SessionSummary

META_PREFIX = "<!-- SEARCH_AGENT_SESSION_META\n"
META_SUFFIX = "\n-->"
MESSAGE_START = "<!-- SEARCH_AGENT_MESSAGE\n"
MESSAGE_END = "\n<!-- /SEARCH_AGENT_MESSAGE -->"
MESSAGE_PATTERN = re.compile(
    r"<!-- SEARCH_AGENT_MESSAGE\n(?P<meta>\{.*?\})\n-->\n(?P<content>.*?)(?=\n<!-- /SEARCH_AGENT_MESSAGE -->)",
    re.DOTALL,
)


class SessionStoreError(Exception):
    pass


class MarkdownSessionStore:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def list_sessions(self) -> list[SessionSummary]:
        sessions: list[SessionSummary] = []
        for path in sorted(self.storage_dir.glob("*.md")):
            detail = self._read_session(path)
            sessions.append(
                SessionSummary(
                    session_id=detail.session_id,
                    title=detail.title,
                    created_at=detail.created_at,
                    updated_at=detail.updated_at,
                    message_count=len(detail.messages),
                    last_message_preview=self._build_preview(detail.messages[-1].content if detail.messages else ""),
                )
            )
        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        return sessions

    def get_session(self, session_id: str) -> SessionDetail | None:
        path = self._path_for(session_id)
        if not path.exists():
            return None
        return self._read_session(path)

    def append_turn(self, session_id: str | None, question: str, answer: str) -> SessionDetail:
        normalized_question = question.strip()
        normalized_answer = answer.strip()
        if not normalized_question:
            raise SessionStoreError("问题不能为空")
        if not normalized_answer:
            raise SessionStoreError("答案不能为空")

        session = self.get_session(session_id) if session_id else None
        now = self._now()

        if session is None:
            new_session_id = session_id or uuid4().hex
            session = SessionDetail(
                session_id=new_session_id,
                title=self._build_title(normalized_question),
                created_at=now,
                updated_at=now,
                message_count=0,
                last_message_preview="",
                messages=[],
            )

        session.messages.append(ConversationMessage(role="user", content=normalized_question, created_at=now))
        session.messages.append(ConversationMessage(role="assistant", content=normalized_answer, created_at=now))
        session.updated_at = now
        session.message_count = len(session.messages)
        session.last_message_preview = self._build_preview(normalized_answer)

        path = self._path_for(session.session_id)
        path.write_text(self._serialize(session), encoding="utf-8")
        return session

    def delete_session(self, session_id: str) -> bool:
        path = self._path_for(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _path_for(self, session_id: str) -> Path:
        return self.storage_dir / f"{session_id}.md"

    def _serialize(self, session: SessionDetail) -> str:
        meta = {
            "session_id": session.session_id,
            "title": session.title,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
        lines = [
            f"{META_PREFIX}{json.dumps(meta, ensure_ascii=False)}{META_SUFFIX}",
            f"# {session.title}",
            "",
            f"- 会话 ID: {session.session_id}",
            f"- 创建时间: {session.created_at}",
            f"- 更新时间: {session.updated_at}",
            "",
            "## 对话记录",
            "",
        ]

        for message in session.messages:
            role_label = "User" if message.role == "user" else "Assistant"
            message_meta = json.dumps(
                {"role": message.role, "created_at": message.created_at},
                ensure_ascii=False,
            )
            lines.extend(
                [
                    f"### {role_label} | {message.created_at}",
                    f"{MESSAGE_START}{message_meta}\n-->",
                    message.content,
                    "<!-- /SEARCH_AGENT_MESSAGE -->",
                    "",
                ]
            )

        return "\n".join(lines).rstrip() + "\n"

    def _read_session(self, path: Path) -> SessionDetail:
        raw = path.read_text(encoding="utf-8")
        meta = self._parse_meta(raw)
        messages = self._parse_messages(raw)
        return SessionDetail(
            session_id=str(meta["session_id"]),
            title=str(meta["title"]),
            created_at=str(meta["created_at"]),
            updated_at=str(meta["updated_at"]),
            message_count=len(messages),
            last_message_preview=self._build_preview(messages[-1].content if messages else ""),
            messages=messages,
        )

    def _parse_meta(self, raw: str) -> dict:
        if not raw.startswith(META_PREFIX):
            raise SessionStoreError("会话文件缺少元数据")
        end_index = raw.find(META_SUFFIX)
        if end_index == -1:
            raise SessionStoreError("会话文件元数据不完整")
        payload = raw[len(META_PREFIX):end_index]
        return json.loads(payload)

    def _parse_messages(self, raw: str) -> list[ConversationMessage]:
        messages: list[ConversationMessage] = []
        for match in MESSAGE_PATTERN.finditer(raw):
            meta = json.loads(match.group("meta"))
            content = match.group("content").strip()
            messages.append(
                ConversationMessage(
                    role=meta["role"],
                    content=content,
                    created_at=meta["created_at"],
                )
            )
        return messages

    def _build_title(self, question: str) -> str:
        normalized = " ".join(question.split())
        if len(normalized) <= 24:
            return normalized
        return f"{normalized[:24].rstrip()}..."

    def _build_preview(self, content: str) -> str:
        normalized = " ".join(content.split())
        if len(normalized) <= 36:
            return normalized
        return f"{normalized[:36].rstrip()}..."

    def _now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="microseconds")
