"""GB-41 headless 20-tick. extract_count == warp_count."""

from __future__ import annotations

import unittest

from skeleton.turn import TICKS, TurnEngine, capabilities


class TestHeadless(unittest.TestCase):
    def test_twenty_ticks(self) -> None:
        card = TurnEngine().run(TICKS)
        self.assertEqual(card["ticks"], 20)
        self.assertEqual(card["extract_count"], card["warp_count"])
        self.assertEqual(card["extract_count"], 1)
        self.assertEqual(card["stored_prose"], 0)

    def test_caps(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["contract"]["warp"], "extract-once")
        self.assertEqual(cap["contract"]["ticks"], 20)


if __name__ == "__main__":
    unittest.main()
