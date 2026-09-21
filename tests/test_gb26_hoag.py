"""GB-26 accept tests."""

from __future__ import annotations

import unittest

from skeleton.hoag import HoagEngine, REGION_N, Warp, bind_mouth_body, capabilities, region_cards
from skeleton.hoag.verify import run_all


class TestPlane(unittest.TestCase):
    def test_twelve_regions(self) -> None:
        cards = region_cards()
        self.assertEqual(len(cards), 12)
        self.assertEqual(REGION_N, 12)
        self.assertEqual(cards[0]["region"], "mouth")
        self.assertEqual(cards[1]["region"], "body")

    def test_warp_once(self) -> None:
        w = Warp()
        self.assertEqual(w.extract("a")["skipped"], 0)
        self.assertEqual(w.extract("b")["skipped"], 1)

    def test_bind(self) -> None:
        self.assertEqual(bind_mouth_body("m", "b")["bound"], 1)


class TestCaps(unittest.TestCase):
    def test_engine(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["contract"]["organism_pwa"], 0)
        snap = HoagEngine().snapshot()
        self.assertEqual(snap["hit"], 1)
        self.assertEqual(run_all()["failed"], [])


if __name__ == "__main__":
    unittest.main()
