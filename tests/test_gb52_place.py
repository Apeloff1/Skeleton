"""GB-52 place tests."""

from __future__ import annotations

import json
import unittest

from skeleton.turn.place import place


class TestPlace(unittest.TestCase):
    def test_token_lands(self) -> None:
        card = place(0, "card-a")
        self.assertEqual(card["ok"], 1)
        self.assertEqual(card["slot"], 0)
        self.assertEqual(card["token"], "card-a")
        self.assertEqual(card["cap"], 8)
        self.assertEqual(card["stored_prose"], 0)

    def test_slot_out_of_range(self) -> None:
        card = place(8, "card-a")
        self.assertEqual(card["ok"], 0)
        self.assertEqual(card["slot"], -1)
        self.assertEqual(card["token"], "")

    def test_bool_and_sentence_refused(self) -> None:
        card = place(True, "has a sentence")
        self.assertEqual(card["ok"], 0)
        self.assertEqual(card["token"], "")
        self.assertNotIn("sentence", json.dumps(card))


if __name__ == "__main__":
    unittest.main()
