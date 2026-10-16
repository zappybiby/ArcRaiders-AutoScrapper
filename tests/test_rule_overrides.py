from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from autoscrapper.config import ProgressSettings
from autoscrapper.core.item_actions import load_item_actions
from autoscrapper.items import rules_store


class RuleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.directory = Path(self.temp_dir.name)
        self.default_path = self.directory / "items_rules.default.json"
        self.custom_path = self.directory / "items_rules.custom.json"
        for name, value in (
            ("DEFAULT_RULES_PATH", self.default_path),
            ("CUSTOM_RULES_PATH", self.custom_path),
        ):
            patcher = patch.object(rules_store, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        progress_patcher = patch.object(
            rules_store, "load_progress_settings", return_value=ProgressSettings()
        )
        self.load_progress = progress_patcher.start()
        self.addCleanup(progress_patcher.stop)
        self.battery = {"id": "battery", "name": "Battery", "action": "sell"}
        self.wire = {"id": "wire", "name": "Wire", "action": "recycle"}
        self.write_defaults(self.battery, self.wire)

    def write_defaults(self, *items: dict) -> None:
        self.default_path.write_text(
            json.dumps({"metadata": {"source": "latest"}, "items": items}),
            encoding="utf-8",
        )

    def actions(self) -> dict[str, str]:
        return {
            item["name"]: item["action"] for item in rules_store.load_rules()["items"]
        }


class RuleOverridesTests(RuleTestCase):
    def test_data_update_preserves_edit_and_updates_untouched_and_new_items(
        self,
    ) -> None:
        rules_store.set_rule_action(self.battery, "keep")
        self.write_defaults(
            {**self.battery, "action": "recycle"},
            {**self.wire, "action": "keep"},
            {"id": "new-item", "name": "New Item", "action": "sell"},
        )

        self.assertEqual(
            {"Battery": "keep", "Wire": "keep", "New Item": "sell"}, self.actions()
        )

    def test_explicit_choice_equal_to_default_remains_pinned(self) -> None:
        rules_store.set_rule_action(self.battery, "sell")
        self.write_defaults({**self.battery, "action": "keep"}, self.wire)

        self.assertEqual("sell", self.actions()["Battery"])
        self.assertTrue(rules_store.is_rule_overridden(self.battery))

    def test_rename_keeps_override_by_id_without_old_name(self) -> None:
        rules_store.set_rule_action(self.battery, "keep")
        self.write_defaults({**self.battery, "name": "Power Cell"}, self.wire)

        self.assertEqual({"Power Cell": "keep", "Wire": "recycle"}, self.actions())
        self.assertEqual(
            {"power cell": ["KEEP"], "wire": ["RECYCLE"]}, load_item_actions()
        )

    def test_removed_item_override_is_dormant_until_same_id_returns(self) -> None:
        rules_store.set_rule_action(self.battery, "keep")
        self.write_defaults(self.wire)
        self.assertEqual({"Wire": "recycle"}, self.actions())

        self.write_defaults({**self.battery, "name": "Power Cell"}, self.wire)
        self.assertEqual("keep", self.actions()["Power Cell"])

    def test_name_entry_for_known_item_updates_it_without_duplicate(self) -> None:
        rules_store.set_rule_action({"name": "  BATTERY  "}, "K")
        self.write_defaults({**self.battery, "name": "Power Cell"}, self.wire)

        self.assertEqual({"Power Cell": "keep", "Wire": "recycle"}, self.actions())

    def test_manual_name_rule_can_be_edited_and_removed(self) -> None:
        rules_store.set_rule_action({"name": "My Trophy"}, "keep")
        rules_store.set_rule_action({"name": " MY TROPHY "}, "sell")

        self.assertEqual(
            {"battery": ["SELL"], "wire": ["RECYCLE"], "my trophy": ["SELL"]},
            load_item_actions(),
        )
        self.assertEqual(3, len(rules_store.load_rules()["items"]))

        rules_store.set_rule_action({"name": "my trophy"}, None)
        self.assertEqual({"Battery": "sell", "Wire": "recycle"}, self.actions())

    def test_manual_name_rule_joins_dataset_item_without_duplicate(self) -> None:
        rules_store.set_rule_action({"name": "My Trophy"}, "keep")
        self.write_defaults(
            self.battery,
            self.wire,
            {"id": "trophy", "name": "My Trophy", "action": "sell"},
        )

        self.assertEqual(3, len(rules_store.load_rules()["items"]))
        self.assertEqual("keep", self.actions()["My Trophy"])

    def test_shared_name_choice_applies_to_current_and_new_variants(self) -> None:
        battery = {**self.battery, "action": "keep"}
        variant = {**battery, "id": "battery-rare", "name": " BATTERY "}
        self.write_defaults(battery, variant)

        rules_store.set_rule_action(battery, "sell")

        self.assertEqual(
            ["sell", "sell"],
            [item["action"] for item in rules_store.load_rules()["items"]],
        )
        self.assertTrue(rules_store.is_rule_overridden(variant))
        self.assertEqual({"battery": ["SELL"]}, load_item_actions())

        new_variant = {**battery, "id": "battery-epic"}
        self.write_defaults(battery, variant, new_variant)
        self.assertEqual(
            ["sell"] * 3, [item["action"] for item in rules_store.load_rules()["items"]]
        )

        rules_store.clear_rule_override(new_variant)
        self.assertEqual(
            ["keep"] * 3, [item["action"] for item in rules_store.load_rules()["items"]]
        )
        self.assertEqual({"battery": ["KEEP"]}, load_item_actions())

    def test_shared_name_skip_and_automatic_cover_every_variant(self) -> None:
        battery = {**self.battery, "action": "keep"}
        variant = {**battery, "id": "battery-rare"}
        self.write_defaults(battery, variant, self.wire)
        self.custom_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "base": "default",
                    "overrides": [{**battery, "action": "sell"}],
                }
            )
        )

        rules_store.set_rule_action(variant, None)
        self.assertEqual({"wire": ["RECYCLE"]}, load_item_actions())

        rules_store.clear_rule_override(battery)
        self.assertEqual(
            {"battery": ["KEEP"], "wire": ["RECYCLE"]}, load_item_actions()
        )

    def test_skip_survives_updates_and_clearing_restores_current_rule(self) -> None:
        rules_store.set_rule_action(self.battery, None)
        updated_battery = {**self.battery, "name": "Power Cell", "action": "keep"}
        self.write_defaults(updated_battery, self.wire)

        self.assertEqual({"Wire": "recycle"}, self.actions())
        self.assertTrue(rules_store.is_rule_overridden(updated_battery))

        rules_store.clear_rule_override(updated_battery)
        self.assertEqual({"Power Cell": "keep", "Wire": "recycle"}, self.actions())
        self.assertFalse(rules_store.is_rule_overridden(updated_battery))

    def test_progress_regeneration_keeps_manual_actions_and_skips(self) -> None:
        rules_store.set_rule_action(self.battery, "keep")
        rules_store.set_rule_action(self.wire, None)
        self.load_progress.return_value = ProgressSettings(completed_quests=["first"])
        new_item = {"id": "new-item", "name": "New Item", "action": "keep"}
        generated = {"metadata": {}, "items": [self.battery, self.wire, new_item]}
        with patch.object(
            rules_store, "generate_rules_from_active", return_value=generated
        ):
            result = rules_store.use_progress_rules()
            self.assertEqual(
                {"Battery": "keep", "New Item": "keep"},
                {item["name"]: item["action"] for item in result["items"]},
            )
            self.assertEqual({"Battery": "keep", "New Item": "keep"}, self.actions())

    def test_saved_progress_changes_recompute_untouched_rules_on_load(self) -> None:
        rules_store.set_rule_action(self.battery, "keep")

        def generate(active, levels, *, completed_quests_override):
            wire_action = (
                "sell" if "wire-quest" in completed_quests_override else "keep"
            )
            return {
                "metadata": {},
                "items": [self.battery, {**self.wire, "action": wire_action}],
            }

        self.load_progress.return_value = ProgressSettings(
            hideout_levels={"workbench": 1}
        )
        with patch.object(
            rules_store, "generate_rules_from_active", side_effect=generate
        ):
            rules_store.use_progress_rules()
            self.assertEqual({"Battery": "keep", "Wire": "keep"}, self.actions())

            self.load_progress.return_value = ProgressSettings(
                completed_quests=["wire-quest"], hideout_levels={"workbench": 1}
            )
            self.assertEqual({"Battery": "keep", "Wire": "sell"}, self.actions())

            self.load_progress.return_value = ProgressSettings()
            self.assertEqual({"Battery": "keep", "Wire": "keep"}, self.actions())
            self.assertEqual(
                {"battery": ["KEEP"], "wire": ["KEEP"]}, load_item_actions()
            )

    def test_scanner_uses_merged_runtime_rules(self) -> None:
        rules_store.set_rule_action(self.battery, "keep")
        rules_store.set_rule_action(self.wire, None)
        self.write_defaults(
            {**self.battery, "action": "recycle"},
            self.wire,
            {"id": "new-item", "name": "New Item", "action": "sell"},
        )

        self.assertEqual(
            {"battery": ["KEEP"], "new item": ["SELL"]}, load_item_actions()
        )

    def test_explicit_external_file_still_loads_legacy_decisions(self) -> None:
        external_path = self.directory / "external.json"
        external_path.write_text(
            json.dumps([{"name": "Other", "decision": ["RECYCLE", "SELL"]}]),
            encoding="utf-8",
        )
        rules_store.set_rule_action(self.battery, "keep")

        self.assertEqual(
            {"other": ["RECYCLE", "SELL"]}, load_item_actions(external_path)
        )


class RuleMigrationTests(RuleTestCase):
    def write_legacy(self) -> bytes:
        payload = {
            "metadata": {"source": "old"},
            "items": [
                {**self.battery, "action": "keep"},
                {"name": "My Trophy", "action": "keep"},
            ],
        }
        original = (json.dumps(payload, indent=4) + "\n").replace("\n", "\r\n").encode()
        self.custom_path.write_bytes(original)
        return original

    def changes_by_name(self, migration) -> dict:
        return {change.name: change for change in migration.changes}

    def test_review_leaves_legacy_rules_and_bytes_unchanged_until_apply(self) -> None:
        original = self.write_legacy()

        migration = rules_store.build_rule_migration()

        self.assertEqual({"Battery": "keep", "My Trophy": "keep"}, self.actions())
        self.assertEqual(original, self.custom_path.read_bytes())
        self.assertEqual(
            [self.custom_path, self.default_path], sorted(self.directory.iterdir())
        )
        self.assertTrue(rules_store.legacy_rules_pending())
        self.assertEqual(
            {"Battery", "Wire", "My Trophy"}, set(self.changes_by_name(migration))
        )
        changes = self.changes_by_name(migration)
        self.assertEqual(
            {**self.battery, "action": "keep"}, changes["Battery"].before_item
        )
        self.assertIsNone(changes["Wire"].before_item)
        self.assertEqual(
            {"name": "My Trophy", "action": "keep"}, changes["My Trophy"].before_item
        )

    def test_migration_backs_up_original_bytes_exactly(self) -> None:
        original = self.write_legacy()

        rules_store.complete_rule_migration(rules_store.build_rule_migration(), set())

        self.assertEqual(
            original, self.custom_path.with_suffix(".legacy.json").read_bytes()
        )
        self.assertFalse(rules_store.legacy_rules_pending())
        self.assertEqual({"Battery": "sell", "Wire": "recycle"}, self.actions())

    def test_select_only_changed_action_as_override(self) -> None:
        self.write_legacy()
        migration = rules_store.build_rule_migration()
        changes = self.changes_by_name(migration)

        rules_store.complete_rule_migration(migration, {changes["Battery"].key})
        self.write_defaults(
            {**self.battery, "action": "recycle"}, {**self.wire, "action": "keep"}
        )

        self.assertEqual({"Battery": "keep", "Wire": "keep"}, self.actions())

    def test_shared_name_has_one_migration_choice_for_all_variants(self) -> None:
        reasons = [
            "Multiple rarities share this name; the scanner can’t distinguish between them."
        ]
        battery = {**self.battery, "action": "keep", "value": 1000, "analysis": reasons}
        variant = {**battery, "id": "battery-rare", "value": 500}
        self.write_defaults(battery, variant)
        for retain in (False, True):
            with self.subTest(retain=retain):
                self.custom_path.write_text(
                    json.dumps(
                        [
                            {**battery, "action": "sell"},
                            {**variant, "action": "recycle"},
                        ]
                    )
                )
                migration = rules_store.build_rule_migration()
                self.assertEqual(1, len(migration.changes))
                change = migration.changes[0]
                self.assertEqual(
                    ("recycle", "keep"), (change.before_action, change.after_action)
                )
                self.assertEqual({**variant, "action": "recycle"}, change.before_item)
                self.assertEqual(
                    {"name": "Battery", "action": "keep", "analysis": reasons},
                    change.item,
                )

                rules_store.complete_rule_migration(
                    migration, {change.key} if retain else set()
                )

                expected = "recycle" if retain else "keep"
                self.assertEqual(
                    [expected, expected],
                    [item["action"] for item in rules_store.load_rules()["items"]],
                )
                self.assertEqual({"battery": [expected.upper()]}, load_item_actions())

    def test_unchanged_shared_name_rules_have_no_migration_differences(self) -> None:
        battery = {**self.battery, "action": "keep"}
        self.write_defaults(battery, {**battery, "id": "battery-rare"})
        self.custom_path.write_bytes(self.default_path.read_bytes())

        self.assertEqual([], rules_store.build_rule_migration().changes)

    def test_select_missing_rule_as_skip_override(self) -> None:
        self.write_legacy()
        migration = rules_store.build_rule_migration()
        changes = self.changes_by_name(migration)

        rules_store.complete_rule_migration(migration, {changes["Wire"].key})

        self.assertEqual({"Battery": "sell"}, self.actions())
        self.assertTrue(rules_store.is_rule_overridden(self.wire))

    def test_select_manual_addition_as_name_override(self) -> None:
        self.write_legacy()
        migration = rules_store.build_rule_migration()
        changes = self.changes_by_name(migration)

        rules_store.complete_rule_migration(migration, {changes["My Trophy"].key})

        self.assertEqual(
            {"Battery": "sell", "Wire": "recycle", "My Trophy": "keep"}, self.actions()
        )

    def test_migration_preserves_valid_legacy_decision_after_invalid_values(
        self,
    ) -> None:
        self.custom_path.write_text(
            json.dumps(
                [
                    {
                        "name": "Battery",
                        "action": "unknown",
                        "decision": ["unknown", "KEEP", "SELL"],
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.assertEqual({"battery": ["KEEP", "SELL"]}, load_item_actions())
        migration = rules_store.build_rule_migration()
        battery_change = self.changes_by_name(migration)["Battery"]
        self.assertEqual("keep", battery_change.before_action)

        rules_store.complete_rule_migration(migration, {battery_change.key})

        self.assertEqual("keep", self.actions()["Battery"])

    def test_invalid_duplicate_row_does_not_replace_effective_legacy_rule(self) -> None:
        self.custom_path.write_text(
            json.dumps(
                [
                    {"name": "Battery", "action": "keep"},
                    {"name": "BATTERY", "action": "unknown"},
                ]
            ),
            encoding="utf-8",
        )
        self.assertEqual({"battery": ["KEEP"]}, load_item_actions())
        migration = rules_store.build_rule_migration()
        battery_change = self.changes_by_name(migration)["Battery"]
        self.assertEqual("keep", battery_change.before_action)

        rules_store.complete_rule_migration(migration, {battery_change.key})

        self.assertEqual("keep", self.actions()["Battery"])

    def test_changed_legacy_file_requires_new_review_without_overwriting(self) -> None:
        self.write_legacy()
        migration = rules_store.build_rule_migration()
        replacement = b'[{"name": "Battery", "action": "recycle"}]\n'
        self.custom_path.write_bytes(replacement)

        with self.assertRaisesRegex(ValueError, "changed"):
            rules_store.complete_rule_migration(migration, set())

        self.assertEqual(replacement, self.custom_path.read_bytes())
        self.assertFalse(self.custom_path.with_suffix(".legacy.json").exists())

    def test_second_migration_preserves_earlier_backup(self) -> None:
        first = self.write_legacy()
        rules_store.complete_rule_migration(rules_store.build_rule_migration(), set())
        second = b'[{"name": "Battery", "action": "recycle"}]\n'
        self.custom_path.write_bytes(second)

        rules_store.complete_rule_migration(rules_store.build_rule_migration(), set())

        self.assertEqual(
            first, self.custom_path.with_suffix(".legacy.json").read_bytes()
        )
        self.assertEqual(
            second, self.custom_path.with_suffix(".legacy-1.json").read_bytes()
        )


if __name__ == "__main__":
    unittest.main()
