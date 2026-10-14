"""ERA-5120 tests. Lazy. No sample bank."""

from __future__ import annotations

import unittest

from skeleton.audio.eras import capabilities, index
from skeleton.audio.eras.caps.c0001_pong_001 import EraPulse, Organ, OrganError
from skeleton.audio.eras.conductor import Conductor
from skeleton.audio.eras.law import CAPABILITY_COUNT


class Era5120Tests(unittest.TestCase):
    def test_count(self) -> None:
        reg = capabilities()
        self.assertEqual(reg["count"], 5120)
        self.assertEqual(reg["count"], CAPABILITY_COUNT)
        self.assertEqual(len(index()), 5120)
        self.assertEqual(len(reg["eras"]), 16)
        self.assertEqual(reg["stored_prose"], 0)
        self.assertEqual(reg["security"]["sample_bank"], 0)

    def test_unique(self) -> None:
        ids = list(index())
        self.assertEqual(ids[0], "ERA5120-0001")
        self.assertEqual(ids[-1], "ERA5120-5120")
        self.assertEqual(len(ids), len(set(ids)))

    def test_polyphony(self) -> None:
        with self.assertRaises(OrganError):
            EraPulse(1, 1, 2, 8000, 1, 0.4)

    def test_rate(self) -> None:
        with self.assertRaises(OrganError):
            EraPulse(1, 1, 1, 44100, 1, 0.4)

    def test_stimulus(self) -> None:
        with self.assertRaises(OrganError):
            EraPulse(1, 1, 1, 8000, 1, 0.4, stimulus="sentence")

    def test_admit_reverse(self) -> None:
        organ = Organ()
        card = organ.admit(EraPulse(1, 1, 1, 8000, 1, 0.4, pointers=("ptr:era",), cool=True))
        self.assertEqual(card["hit"], 1)
        self.assertIsNotNone(organ.reverse())

    def test_eras(self) -> None:
        cards = Conductor().pulse_eras()
        self.assertEqual(len(cards), 16)

    def test_double_prior(self) -> None:
        self.assertEqual(CAPABILITY_COUNT, 2560 * 2)


if __name__ == "__main__":
    unittest.main()
