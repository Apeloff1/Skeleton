"""AUD-1280 fail-closed tests. No network."""

from __future__ import annotations

import unittest

from skeleton.audio.vol156 import Conductor, capabilities, index
from skeleton.audio.vol156.caps.c0001_asset_01 import EnvelopePulse, OrganError
from skeleton.audio.vol156.law import CAPABILITY_COUNT

DIGEST = "ef" * 32


class Audio1280Tests(unittest.TestCase):
    def test_count(self) -> None:
        reg = capabilities()
        self.assertEqual(reg["count"], 1280)
        self.assertEqual(reg["count"], CAPABILITY_COUNT)
        self.assertEqual(len(index()), 1280)
        self.assertEqual(reg["stored_prose"], 0)
        self.assertEqual(reg["security"]["coin"], 0)
        self.assertEqual(reg["security"]["network"], 0)

    def test_unique(self) -> None:
        ids = [item["id"] for item in capabilities()["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "AUD1280-0001")
        self.assertEqual(ids[-1], "AUD1280-1280")

    def test_families(self) -> None:
        fams = {item["contract"]["family"] for item in capabilities()["items"]}
        self.assertEqual(len(fams), 16)

    def test_pulse_reverse(self) -> None:
        deck = Conductor()
        cards = deck.pulse_all(1, 1)
        self.assertEqual(len(cards), 1280)
        self.assertTrue(all(c.get("stored_prose", 0) == 0 for c in cards))
        self.assertGreater(deck.snapshot()["mass"], 0)
        self.assertGreater(deck.reverse_all(), 0)

    def test_stale(self) -> None:
        deck = Conductor()
        cards = deck.pulse_all(2, 1)
        self.assertTrue(any(c.get("hit") == 0 for c in cards))

    def test_bad_asset(self) -> None:
        with self.assertRaises(OrganError):
            EnvelopePulse(1, 1, "bad id", 48000, 2, 0, 20, 1000, "event", 0.5, DIGEST)

    def test_segment(self) -> None:
        with self.assertRaises(OrganError):
            EnvelopePulse(1, 1, "ASSET-VOL156", 48000, 2, 50, 40, 1000, "event", 0.5, DIGEST)

    def test_kind(self) -> None:
        with self.assertRaises(OrganError):
            EnvelopePulse(1, 1, "ASSET-VOL156", 48000, 2, 0, 20, 1000, "noise", 0.5, DIGEST)

    def test_rate(self) -> None:
        with self.assertRaises(OrganError):
            EnvelopePulse(1, 1, "ASSET-VOL156", 192000, 2, 0, 20, 1000, "music", 0.5, DIGEST)

    def test_double_prior(self) -> None:
        self.assertEqual(CAPABILITY_COUNT, 640 * 2)


if __name__ == "__main__":
    unittest.main()
