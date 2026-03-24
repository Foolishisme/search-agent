import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.schemas import (
    ConversationMessage,
    RuntimeLog,
    SearchResult,
    SessionDetail,
    SessionSummary,
    SessionTurn,
    ToolObservation,
)

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

    def append_turn(
        self,
        session_id: str | None,
        question: str,
        answer: str,
        *,
        need_search: bool,
        query: str | None,
        logs: list[RuntimeLog],
        search_results: list[SearchResult],
        tool_observations: list[ToolObservation],
    ) -> SessionDetail:
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
                turns=[],
                latest_logs=[],
                latest_search_results=[],
                latest_tool_observations=[],
            )

        turn = SessionTurn(
            created_at=now,
            question=normalized_question,
            answer=normalized_answer,
            need_search=need_search,
            query=query,
            logs=[RuntimeLog.model_validate(item) for item in logs],
            search_results=[SearchResult.model_validate(item) for item in search_results],
            tool_observations=[ToolObservation.model_validate(item) for item in tool_observations],
        )
        session.turns.append(turn)
        session.messages = self._messages_from_turns(session.turns)
        session.updated_at = now
        session.message_count = len(session.messages)
        session.last_message_preview = self._build_preview(normalized_answer)
        session.latest_logs = turn.logs
        session.latest_search_results = turn.search_results
        session.latest_tool_observations = turn.tool_observations

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
            "turns": [turn.model_dump(mode="json") for turn in session.turns],
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

        for turn in session.turns:
            lines.extend(
                [
                    f"### User | {turn.created_at}",
                    f'{MESSAGE_START}{json.dumps({"role": "user", "created_at": turn.created_at}, ensure_ascii=False)}\n-->',
                    turn.question,
                    "<!-- /SEARCH_AGENT_MESSAGE -->",
                    "",
                    f"### Assistant | {turn.created_at}",
                    f'{MESSAGE_START}{json.dumps({"role": "assistant", "created_at": turn.created_at}, ensure_ascii=False)}\n-->',
                    turn.answer,
                    "<!-- /SEARCH_AGENT_MESSAGE -->",
                    "",
                ]
            )

        return "\n".join(lines).rstrip() + "\n"

    def _read_session(self, path: Path) -> SessionDetail:
        raw = path.read_text(encoding="utf-8")
        meta = self._parse_meta(raw)
        turns = self._parse_turns(meta, raw)
        messages = self._messages_from_turns(turns)
        latest_turn = turns[-1] if turns else None
        return SessionDetail(
            session_id=str(meta["session_id"]),
            title=str(meta["title"]),
            created_at=str(meta["created_at"]),
            updated_at=str(meta["updated_at"]),
            message_count=len(messages),
            last_message_preview=self._build_preview(messages[-1].content if messages else ""),
            messages=messages,
            turns=turns,
            latest_logs=latest_turn.logs if latest_turn else [],
            latest_search_results=latest_turn.search_results if latest_turn else [],
            latest_tool_observations=latest_turn.tool_observations if latest_turn else [],
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

    def _parse_turns(self, meta: dict, raw: str) -> list[SessionTurn]:
        serialized_turns = meta.get("turns")
        if isinstance(serialized_turns, list):
            return [SessionTurn.model_validate(item) for item in serialized_turns]

        messages = self._parse_messages(raw)
        turns: list[SessionTurn] = []
        for index in range(0, len(messages), 2):
            if index + 1 >= len(messages):
                break
            user_message = messages[index]
            assistant_message = messages[index + 1]
            if user_message.role != "user" or assistant_message.role != "assistant":
                continue
            turns.append(
                SessionTurn(
                    created_at=assistant_message.created_at,
                    question=user_message.content,
                    answer=assistant_message.content,
                    need_search=False,
                    query=None,
                    logs=[],
                    search_results=[],
                    tool_observations=[],
                )
            )
        return turns

    def _messages_from_turns(self, turns: list[SessionTurn]) -> list[ConversationMessage]:
        messages: list[ConversationMessage] = []
        for turn in turns:
            messages.append(
                ConversationMessage(role="user", content=turn.question, created_at=turn.created_at)
            )
            messages.append(
                ConversationMessage(role="assistant", content=turn.answer, created_at=turn.created_at)
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
