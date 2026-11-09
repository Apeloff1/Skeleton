"""GB-55 decode tests."""

from __future__ import annotations

import json
import unittest

from skeleton.turn.decode import decode


class TestDecode(unittest.TestCase):
    def test_r2_passes(self) -> None:
        card = decode("r2")
        self.assertEqual(card["ok"], 1)
        self.assertEqual(card["r"], 2)
        self.assertEqual(card["halt"], 0)
        self.assertEqual(card["stored_prose"], 0)

    def test_r3_needs_halt(self) -> None:
        blocked = decode("r3halt", 0)
        self.assertEqual(blocked["ok"], 0)
        self.assertEqual(blocked["depth"], "")
        opened = decode("r3halt", 1)
        self.assertEqual(opened["ok"], 1)
        self.assertEqual(opened["r"], 3)

    def test_bool_and_sentence_refused(self) -> None:
        card = decode("has a sentence", True)
        self.assertEqual(card["ok"], 0)
        self.assertEqual(card["depth"], "")
        self.assertNotIn("sentence", json.dumps(card))


if __name__ == "__main__":
    unittest.main()
