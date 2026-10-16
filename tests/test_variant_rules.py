from __future__ import annotations

import unittest

from autoscrapper.progress.decision_engine import DecisionEngine


class VariantRulesTests(unittest.TestCase):
    def engine(self, items: list[dict]) -> DecisionEngine:
        return DecisionEngine(items, [], [], [])

    def test_distinct_variants_are_kept_even_when_each_would_be_sold(self) -> None:
        items = [
            {"id": "chair-blue", "name": "Study Armchair", "value": 100},
            {"id": "chair-red", "name": " study armchair ", "value": 200},
        ]
        for item in items:
            self.assertEqual(
                "sell_or_recycle", self.engine([item]).get_decision(item, {}).decision
            )

        for ordered_items in (items, list(reversed(items))):
            with self.subTest(order=[item["id"] for item in ordered_items]):
                decisions = self.engine(ordered_items).get_items_with_decisions({})
                self.assertEqual(
                    ["keep", "keep"],
                    [item["decision_data"].decision for item in decisions],
                )

    def test_repeated_same_id_does_not_count_as_another_variant(self) -> None:
        item = {"id": "chair", "name": "Study Armchair", "value": 100}
        decisions = self.engine([item, dict(item)]).get_items_with_decisions({})

        self.assertEqual(1, len(decisions))
        self.assertEqual("sell_or_recycle", decisions[0]["decision_data"].decision)

    def test_unique_items_keep_their_existing_decisions(self) -> None:
        items = [
            {"id": "chair-blue", "name": "Study Armchair"},
            {"id": "chair-red", "name": "Study Armchair"},
            {"id": "scrap", "name": "Scrap", "value": 100},
            {"id": "rare-find", "name": "Rare Find", "rarity": "legendary"},
        ]
        engine = self.engine(items)

        for item in items[2:]:
            with self.subTest(item=item["id"]):
                self.assertEqual(
                    self.engine([item]).get_decision(item, {}),
                    engine.get_decision(item, {}),
                )


if __name__ == "__main__":
    unittest.main()
