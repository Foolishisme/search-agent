import json
import re
from pathlib import Path

from app.schemas import SkillContext, SkillCreateRequest, SkillDetail, SkillSummary, SkillUpdateRequest


class AgentConfigStoreError(RuntimeError):
    pass


class AgentConfigStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.skills_dir = self.base_dir / "skills"
        self.index_path = self.skills_dir / "index.json"
        self.rules_path = self.base_dir / "rules.md"
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        if not self.rules_path.exists():
            self.rules_path.write_text("", encoding="utf-8")
        if not self.index_path.exists():
            default_skill_id = "search-basics-1"
            self._skill_path(default_skill_id).parent.mkdir(parents=True, exist_ok=True)
            self._skill_path(default_skill_id).write_text(
                "# Search Basics\n\n"
                "- Prefer explicit dates and named entities.\n"
                "- If public information is insufficient, say so plainly.\n"
                "- Avoid repeating the same query without adjustment.\n",
                encoding="utf-8",
            )
            self._write_index(
                {
                    "next_seq": 2,
                    "skills": [
                        {
                            "seq": 1,
                            "skill_id": default_skill_id,
                            "name": "Search Basics",
                            "description": "基础搜索与收口规则",
                            "enabled": True,
                        }
                    ],
                }
            )

    def load_rules(self) -> str:
        self._ensure_layout()
        return self.rules_path.read_text(encoding="utf-8")

    def save_rules(self, content: str) -> str:
        self._ensure_layout()
        self.rules_path.write_text(content or "", encoding="utf-8")
        return self.load_rules()

    def list_skills(self) -> list[SkillSummary]:
        index = self._read_index()
        skills = [SkillSummary.model_validate(item) for item in index["skills"]]
        return sorted(skills, key=lambda item: item.seq)

    def list_enabled_skill_summaries(self) -> list[SkillSummary]:
        return [item for item in self.list_skills() if item.enabled]

    def get_skill(self, skill_id: str) -> SkillDetail | None:
        index = self._read_index()
        record = self._find_record(index, skill_id)
        if record is None:
            return None
        content = self._skill_path(skill_id).read_text(encoding="utf-8") if self._skill_path(skill_id).exists() else ""
        return SkillDetail(
            seq=record["seq"],
            skill_id=record["skill_id"],
            name=record["name"],
            description=record["description"],
            enabled=bool(record.get("enabled", True)),
            content=content,
        )

    def create_skill(self, payload: SkillCreateRequest) -> SkillDetail:
        index = self._read_index()
        seq = int(index.get("next_seq", 1))
        slug = self._slugify(payload.name)
        skill_id = f"{slug}-{seq}"
        record = {
            "seq": seq,
            "skill_id": skill_id,
            "name": payload.name.strip(),
            "description": payload.description.strip(),
            "enabled": payload.enabled,
        }
        index["skills"].append(record)
        index["next_seq"] = seq + 1
        self._skill_path(skill_id).parent.mkdir(parents=True, exist_ok=True)
        self._skill_path(skill_id).write_text(payload.content or "", encoding="utf-8")
        self._write_index(index)
        return self.get_skill(skill_id)  # type: ignore[return-value]

    def update_skill(self, skill_id: str, payload: SkillUpdateRequest) -> SkillDetail:
        index = self._read_index()
        record = self._find_record(index, skill_id)
        if record is None:
            raise AgentConfigStoreError("Skill not found")
        record["name"] = payload.name.strip()
        record["description"] = payload.description.strip()
        record["enabled"] = payload.enabled
        self._skill_path(skill_id).parent.mkdir(parents=True, exist_ok=True)
        self._skill_path(skill_id).write_text(payload.content or "", encoding="utf-8")
        self._write_index(index)
        return self.get_skill(skill_id)  # type: ignore[return-value]

    def delete_skill(self, skill_id: str) -> bool:
        index = self._read_index()
        before = len(index["skills"])
        index["skills"] = [item for item in index["skills"] if item["skill_id"] != skill_id]
        if len(index["skills"]) == before:
            return False
        self._write_index(index)
        skill_path = self._skill_path(skill_id)
        if skill_path.exists():
            skill_path.unlink()
        skill_dir = skill_path.parent
        if skill_dir.exists():
            try:
                skill_dir.rmdir()
            except OSError:
                pass
        return True

    def load_skill_contexts(self, skill_ids: list[str]) -> list[SkillContext]:
        contexts: list[SkillContext] = []
        enabled = {item.skill_id: item for item in self.list_enabled_skill_summaries()}
        for skill_id in skill_ids:
            summary = enabled.get(skill_id)
            if summary is None:
                continue
            detail = self.get_skill(skill_id)
            if detail is None:
                continue
            contexts.append(
                SkillContext(
                    skill_id=detail.skill_id,
                    name=detail.name,
                    description=detail.description,
                    content=detail.content,
                )
            )
        return contexts

    def _read_index(self) -> dict:
        self._ensure_layout()
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AgentConfigStoreError("Skill index is invalid JSON") from exc

    def _write_index(self, payload: dict) -> None:
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _find_record(self, index: dict, skill_id: str) -> dict | None:
        for item in index["skills"]:
            if item["skill_id"] == skill_id:
                return item
        return None

    def _skill_path(self, skill_id: str) -> Path:
        return self.skills_dir / skill_id / "SKILL.md"

    def _slugify(self, value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip().lower()).strip("-")
        return normalized or "skill"
