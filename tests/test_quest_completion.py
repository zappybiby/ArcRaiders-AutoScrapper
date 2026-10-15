from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from autoscrapper.progress.rules_generator import generate_rules_from_active


class QuestCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.data_dir = Path(self.temp_dir.name)
        (self.data_dir / "static").mkdir()
        snapshot = {
            "items.json": [
                {"id": "air-freshener", "name": "Air Freshener", "value": 2000}
            ],
            "quests.json": [
                {"id": "old-quest", "name": "Old quest", "requirements": []},
                {
                    "id": "new-quest",
                    "name": "New quest",
                    "requirements": [{"item_id": "air-freshener", "quantity": 1}],
                },
            ],
            "quests_graph.json": {"nodes": {}, "edges": []},
            "static/hideout_modules.json": [],
            "static/projects.json": [],
        }
        for filename, payload in snapshot.items():
            (self.data_dir / filename).write_text(json.dumps(payload), encoding="utf-8")

    def generate(self, **kwargs) -> dict:
        return generate_rules_from_active(
            kwargs.pop("active_quests", []), {}, data_dir=self.data_dir, **kwargs
        )

    def test_saved_completion_does_not_complete_new_quest(self) -> None:
        result = self.generate(
            all_quests_completed=True, completed_quests_override=["old-quest"]
        )

        self.assertEqual("keep", result["items"][0]["action"])
        self.assertIn("Required for quest: New quest", result["items"][0]["analysis"])
        self.assertNotIn("allQuestsCompleted", result["metadata"])

    def test_explicit_empty_completion_does_not_use_all_completed_flag(self) -> None:
        result = self.generate(all_quests_completed=True, completed_quests_override=[])

        self.assertEqual("keep", result["items"][0]["action"])
        self.assertNotIn("allQuestsCompleted", result["metadata"])

    def test_explicit_all_completed_still_uses_current_quests(self) -> None:
        result = self.generate(all_quests_completed=True)

        self.assertEqual("sell", result["items"][0]["action"])
        self.assertTrue(result["metadata"]["allQuestsCompleted"])

    def test_saved_completion_can_cover_all_current_quests(self) -> None:
        result = self.generate(completed_quests_override=["old-quest", "new-quest"])

        self.assertEqual("sell", result["items"][0]["action"])
        self.assertTrue(result["metadata"]["allQuestsCompleted"])

    def test_removed_active_quest_does_not_block_saved_completion(self) -> None:
        result = self.generate(
            active_quests=["removed-quest"],
            completed_quests_override=["old-quest"],
        )

        self.assertEqual("keep", result["items"][0]["action"])
        self.assertNotIn("activeQuests", result["metadata"])

    def test_missing_active_quest_still_blocks_inference(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "Active quests not found: removed-quest"
        ):
            self.generate(active_quests=["removed-quest"])


if __name__ == "__main__":
    unittest.main()
