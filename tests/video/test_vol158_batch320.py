"""VID-320 fail-closed tests. No network."""

from __future__ import annotations

import unittest

from skeleton.video.vol158 import Conductor, capabilities, index
from skeleton.video.vol158.caps.c001_asset_01 import FramePulse, OrganError
from skeleton.video.vol158.law import CAPABILITY_COUNT

DIGEST = "ab" * 32


class Video320Tests(unittest.TestCase):
    def test_count(self) -> None:
        reg = capabilities()
        self.assertEqual(reg["count"], 320)
        self.assertEqual(reg["count"], CAPABILITY_COUNT)
        self.assertEqual(len(index()), 320)
        self.assertEqual(reg["stored_prose"], 0)
        self.assertEqual(reg["security"]["coin"], 0)
        self.assertEqual(reg["security"]["network"], 0)

    def test_unique(self) -> None:
        ids = [item["id"] for item in capabilities()["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "VID320-001")
        self.assertEqual(ids[-1], "VID320-320")

    def test_families(self) -> None:
        fams = {item["contract"]["family"] for item in capabilities()["items"]}
        self.assertEqual(len(fams), 16)

    def test_pulse_reverse(self) -> None:
        deck = Conductor()
        cards = deck.pulse_all(1, 1, keyframe=True)
        self.assertEqual(len(cards), 320)
        self.assertTrue(all(c.get("stored_prose", 0) == 0 for c in cards))
        self.assertGreater(deck.snapshot()["mass"], 0)
        self.assertGreater(deck.reverse_all(), 0)

    def test_stale(self) -> None:
        deck = Conductor()
        cards = deck.pulse_all(2, 1)
        self.assertTrue(any(c.get("hit") == 0 for c in cards))

    def test_bad_asset(self) -> None:
        with self.assertRaises(OrganError):
            FramePulse(1, 1, "bad id", 640, 360, 0, DIGEST)

    def test_pixel_cap(self) -> None:
        with self.assertRaises(OrganError):
            FramePulse(1, 1, "ASSET-VOL158", 4000, 3000, 0, DIGEST)

    def test_double_prior(self) -> None:
        self.assertEqual(CAPABILITY_COUNT, 160 * 2)


if __name__ == "__main__":
    unittest.main()
