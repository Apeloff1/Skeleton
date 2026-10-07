"""GB-54 prefill tests."""

from __future__ import annotations

import json
import unittest

from skeleton.turn.prefill import prefill


class TestPrefill(unittest.TestCase):
    def test_empty_slots(self) -> None:
        card = prefill([1, 4], "pad")
        self.assertEqual(card["ok"], 1)
        self.assertEqual(card["slots"], [0, 2, 3, 5, 6, 7])
        self.assertEqual(card["n"], 6)
        self.assertEqual(card["dropped"], 0)
        self.assertEqual(card["stored_prose"], 0)

    def test_sentence_fill_refused(self) -> None:
        card = prefill([0], "has a sentence")
        self.assertEqual(card["ok"], 0)
        self.assertEqual(card["slots"], [])
        self.assertNotIn("sentence", json.dumps(card))

    def test_bad_occupied_dropped(self) -> None:
        card = prefill(["has a sentence", True, 9, 2], "pad")
        self.assertEqual(card["ok"], 1)
        self.assertEqual(card["dropped"], 3)
        self.assertNotIn(2, card["slots"])
        self.assertNotIn("sentence", json.dumps(card))


if __name__ == "__main__":
    unittest.main()
