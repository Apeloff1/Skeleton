"""CUE-2560 fail-closed tests. Lazy. No mass import."""

from __future__ import annotations

import unittest

from skeleton.cue.gb46 import capabilities, index
from skeleton.cue.gb46.caps.c0001_house_001 import CuePulse, Organ, OrganError
from skeleton.cue.gb46.conductor import Conductor
from skeleton.cue.gb46.law import CAPABILITY_COUNT


class Cue2560Tests(unittest.TestCase):
    def test_count(self) -> None:
        reg = capabilities()
        self.assertEqual(reg["count"], 2560)
        self.assertEqual(reg["count"], CAPABILITY_COUNT)
        self.assertEqual(len(index()), 2560)
        self.assertEqual(reg["stored_prose"], 0)
        self.assertEqual(reg["security"]["coin"], 0)
        self.assertEqual(len(reg["families"]), 16)

    def test_unique(self) -> None:
        ids = list(index())
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "CUE2560-0001")
        self.assertEqual(ids[-1], "CUE2560-2560")

    def test_bad_house(self) -> None:
        with self.assertRaises(OrganError):
            CuePulse(1, 1, "nope", "forge", "r1", "proof", "mla")

    def test_stimulus(self) -> None:
        with self.assertRaises(OrganError):
            CuePulse(1, 1, "github", "forge", "r1", "proof", "mla", stimulus="sentence")

    def test_admit_reverse(self) -> None:
        organ = Organ()
        pulse = CuePulse(1, 1, "github", "forge", "r1", "proof", "mla", pointers=("ptr:axis",), cool=True)
        card = organ.admit(pulse)
        self.assertEqual(card["hit"], 1)
        self.assertEqual(card["stored_prose"], 0)
        self.assertIsNotNone(organ.reverse())

    def test_sample(self) -> None:
        cards = Conductor().pulse_sample(160)
        self.assertEqual(len(cards), 16)
        self.assertTrue(all(c.get("stored_prose", 0) == 0 for c in cards))

    def test_double_prior(self) -> None:
        self.assertEqual(CAPABILITY_COUNT, 1280 * 2)


if __name__ == "__main__":
    unittest.main()
