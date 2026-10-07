"""GB-56 reclaim tests."""

from __future__ import annotations

import json
import unittest

from skeleton.turn.reclaim import reclaim


class TestReclaim(unittest.TestCase):
    def test_frees_held(self) -> None:
        card = reclaim([0, 1, 4], [1, 4])
        self.assertEqual(card["ok"], 1)
        self.assertEqual(card["slots"], [1, 4])
        self.assertEqual(card["remain"], [0])
        self.assertEqual(card["missed"], 0)
        self.assertEqual(card["stored_prose"], 0)

    def test_unheld_misses(self) -> None:
        card = reclaim([0], [3])
        self.assertEqual(card["ok"], 0)
        self.assertEqual(card["slots"], [])
        self.assertEqual(card["remain"], [0])
        self.assertEqual(card["missed"], 1)

    def test_sentence_and_dup_drop(self) -> None:
        card = reclaim([1, 1], [1, "has a sentence", True])
        self.assertEqual(card["ok"], 1)
        self.assertEqual(card["slots"], [1])
        self.assertEqual(card["collision"], 1)
        self.assertEqual(card["dropped"], 2)
        self.assertNotIn("sentence", json.dumps(card))


if __name__ == "__main__":
    unittest.main()
