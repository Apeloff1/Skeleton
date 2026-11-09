"""DV-640 fail-closed tests. No network. No stored sentence."""

from __future__ import annotations

import unittest

from skeleton.document_vision.vol155 import Conductor, capabilities, index
from skeleton.document_vision.vol155.caps.c001_page_01 import OrganError, SpanPulse
from skeleton.document_vision.vol155.law import CAPABILITY_COUNT

DIGEST = "cd" * 32


class Vision640Tests(unittest.TestCase):
    def test_count(self) -> None:
        reg = capabilities()
        self.assertEqual(reg["count"], 640)
        self.assertEqual(reg["count"], CAPABILITY_COUNT)
        self.assertEqual(len(index()), 640)
        self.assertEqual(reg["stored_prose"], 0)
        self.assertEqual(reg["security"]["coin"], 0)
        self.assertEqual(reg["security"]["network"], 0)

    def test_unique(self) -> None:
        ids = [item["id"] for item in capabilities()["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "DV640-001")
        self.assertEqual(ids[-1], "DV640-640")

    def test_families(self) -> None:
        fams = {item["contract"]["family"] for item in capabilities()["items"]}
        self.assertEqual(len(fams), 16)

    def test_pulse_reverse(self) -> None:
        deck = Conductor()
        cards = deck.pulse_all(1, 1)
        self.assertEqual(len(cards), 640)
        self.assertTrue(all(c.get("stored_prose", 0) == 0 for c in cards))
        self.assertGreater(deck.snapshot()["mass"], 0)
        self.assertGreater(deck.reverse_all(), 0)

    def test_stale(self) -> None:
        deck = Conductor()
        cards = deck.pulse_all(2, 1)
        self.assertTrue(any(c.get("hit") == 0 for c in cards))

    def test_bad_page(self) -> None:
        with self.assertRaises(OrganError):
            SpanPulse(1, 1, "bad id", 1, 0, 0, 10, 10, 100, 100, DIGEST, 0.5)

    def test_region_oob(self) -> None:
        with self.assertRaises(OrganError):
            SpanPulse(1, 1, "DOC-VOL155", 1, 90, 0, 20, 10, 100, 100, DIGEST, 0.5)

    def test_confidence(self) -> None:
        with self.assertRaises(OrganError):
            SpanPulse(1, 1, "DOC-VOL155", 1, 0, 0, 10, 10, 100, 100, DIGEST, 1.4)

    def test_double_prior(self) -> None:
        self.assertEqual(CAPABILITY_COUNT, 320 * 2)


if __name__ == "__main__":
    unittest.main()
