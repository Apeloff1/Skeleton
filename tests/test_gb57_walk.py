"""GB-57 walk tests."""

from __future__ import annotations

import json
import unittest

from skeleton.turn.walk import walk


class TestWalk(unittest.TestCase):
    def test_prefix_passes(self) -> None:
        card = walk(["admit", "quota", "place"])
        self.assertEqual(card["ok"], 1)
        self.assertEqual(card["n"], 3)
        self.assertEqual(card["steps"], ["admit", "quota", "place"])
        self.assertEqual(card["stored_prose"], 0)

    def test_skip_refused(self) -> None:
        card = walk(["admit", "place"])
        self.assertEqual(card["ok"], 0)
        self.assertEqual(card["steps"], [])
        self.assertEqual(card["dropped"], 0)

    def test_sentence_not_stored(self) -> None:
        card = walk(["admit", "has a sentence"])
        self.assertEqual(card["ok"], 0)
        self.assertEqual(card["dropped"], 1)
        self.assertEqual(card["steps"], [])
        self.assertNotIn("sentence", json.dumps(card))


if __name__ == "__main__":
    unittest.main()
