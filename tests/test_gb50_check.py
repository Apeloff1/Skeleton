"""GB-50 check tests."""

from __future__ import annotations

import json
import unittest

from skeleton.turn.check import check


class TestCheck(unittest.TestCase):
    def test_move_passes(self) -> None:
        card = check({"stamp": 0, "rebuild": 0, "note": "see the long sentence"})
        self.assertEqual(card["ok"], 1)
        self.assertEqual(card["stamp"], 0)
        self.assertEqual(card["rebuild"], 0)
        self.assertEqual(card["stored_prose"], 0)
        self.assertNotIn("sentence", json.dumps(card))

    def test_stamp_fails(self) -> None:
        card = check({"stamp": 1, "rebuild": 0})
        self.assertEqual(card["ok"], 0)
        self.assertEqual(card["stamp"], 1)

    def test_rebuild_fails(self) -> None:
        card = check({"stamp": 0, "rebuild": 1})
        self.assertEqual(card["ok"], 0)
        self.assertEqual(card["rebuild"], 1)


if __name__ == "__main__":
    unittest.main()
