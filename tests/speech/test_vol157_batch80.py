"""SPEECH-80 fail-closed tests. No network."""

from __future__ import annotations

import unittest

from skeleton.speech.vol157 import Conductor, capabilities, index
from skeleton.speech.vol157.caps.c01_generation_fence import OrganError, Pulse
from skeleton.speech.vol157.law import CAPABILITY_COUNT, HEAT_DROP


class Speech80Tests(unittest.TestCase):
    def test_count(self) -> None:
        reg = capabilities()
        self.assertEqual(reg["count"], 80)
        self.assertEqual(reg["count"], CAPABILITY_COUNT)
        self.assertEqual(len(index()), 80)
        self.assertEqual(reg["stored_prose"], 0)
        self.assertEqual(reg["security"]["network"], 0)
        self.assertEqual(reg["security"]["coin"], 0)

    def test_unique_ids(self) -> None:
        ids = [item["id"] for item in capabilities()["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "SP80-01")
        self.assertEqual(ids[-1], "SP80-80")

    def test_pulse_and_reverse(self) -> None:
        deck = Conductor()
        cards = deck.pulse_all(1, 1, 0.2, ("ptr:vad", "ptr:spk"))
        self.assertEqual(len(cards), 80)
        for card in cards:
            self.assertEqual(card.get("stored_prose", 0), 0)
        snap = deck.snapshot()
        self.assertEqual(snap["count"], 80)
        self.assertGreater(snap["mass"], 0)
        n = deck.reverse_all()
        self.assertGreater(n, 0)

    def test_stale_generation(self) -> None:
        deck = Conductor()
        cards = deck.pulse_all(2, 1, 0.1, ("ptr:gen",))
        rejects = [c for c in cards if c.get("hit") == 0]
        self.assertGreater(len(rejects), 0)

    def test_ncap(self) -> None:
        with self.assertRaises(OrganError):
            Pulse(1, 1, 0.1, tuple(f"p{i}" for i in range(9)))

    def test_heat_constant(self) -> None:
        self.assertGreater(HEAT_DROP, 0.5)

    def test_family_coverage(self) -> None:
        fams = {item["contract"]["family"] for item in capabilities()["items"]}
        self.assertEqual(len(fams), 10)


if __name__ == "__main__":
    unittest.main()
