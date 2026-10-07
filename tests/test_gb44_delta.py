"""GB-44 delta tests."""

from __future__ import annotations

import unittest

from skeleton.turn.delta import delta


class TestDelta(unittest.TestCase):
    def test_moved_is_not_a_stamp(self) -> None:
        card = delta(
            {"ticks": 0, "extract_count": 0, "warp_count": 0},
            {"ticks": 20, "extract_count": 1, "warp_count": 1},
        )
        self.assertEqual(card["stamp"], 0)
        self.assertEqual(card["rebuild"], 0)
        self.assertEqual(card["moved"]["ticks"], 20)
        self.assertEqual(card["stored_prose"], 0)

    def test_identical_is_a_stamp(self) -> None:
        same = {"ticks": 20, "extract_count": 1, "warp_count": 1}
        card = delta(same, dict(same))
        self.assertEqual(card["stamp"], 1)
        self.assertEqual(card["rebuild"], 0)


if __name__ == "__main__":
    unittest.main()
