import tempfile
import unittest
from pathlib import Path

from app.agent_config_store import AgentConfigStore
from app.schemas import SkillCreateRequest, SkillUpdateRequest


class AgentConfigStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = AgentConfigStore(Path(self.tempdir.name))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_rules_default_to_empty_file(self):
        self.assertEqual(self.store.load_rules(), "")
        self.assertTrue((Path(self.tempdir.name) / "rules.md").exists())
        self.assertEqual(len(self.store.list_skills()), 1)

    def test_create_update_delete_skill(self):
        created = self.store.create_skill(
            SkillCreateRequest(name="Search", description="Search guidance", content="Use precise dates.", enabled=True)
        )
        self.assertEqual(created.seq, 2)
        self.assertEqual(created.skill_id, "search-2")
        self.assertEqual(len(self.store.list_skills()), 2)

        updated = self.store.update_skill(
            created.skill_id,
            SkillUpdateRequest(name="Search Updated", description="New desc", content="Updated content", enabled=False),
        )
        self.assertEqual(updated.name, "Search Updated")
        self.assertFalse(updated.enabled)
        self.assertEqual(len(self.store.list_enabled_skill_summaries()), 1)

        contexts = self.store.load_skill_contexts([created.skill_id])
        self.assertEqual(contexts, [])

        self.assertTrue(self.store.delete_skill(created.skill_id))
        self.assertEqual(len(self.store.list_skills()), 1)
