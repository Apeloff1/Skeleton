"""GB-53 stock tests."""

from __future__ import annotations

import json
import unittest

from skeleton.turn.stock import stock


class TestStock(unittest.TestCase):
    def test_unique_slots(self) -> None:
        card = stock([
            {"slot": 1, "token": "card-a"},
            {"slot": 4, "token": "card-b"},
        ])
        self.assertEqual(card["n"], 2)
        self.assertEqual(card["slots"], [1, 4])
        self.assertEqual(card["collision"], 0)
        self.assertEqual(card["dropped"], 0)
        self.assertEqual(card["stored_prose"], 0)

    def test_collision_and_sentence(self) -> None:
        card = stock([
            {"slot": 1, "token": "card-a"},
            {"slot": 1, "token": "card-b"},
            {"slot": 2, "token": "has a sentence"},
            {"slot": True, "token": "card-c"},
        ])
        self.assertEqual(card["n"], 1)
        self.assertEqual(card["slots"], [1])
        self.assertEqual(card["collision"], 1)
        self.assertEqual(card["dropped"], 2)
        self.assertNotIn("sentence", json.dumps(card))


if __name__ == "__main__":
    unittest.main()
