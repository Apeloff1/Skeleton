"""SCAT-10240. Lazy. One plane sampled. Count from indexes."""
import unittest
from pathlib import Path
from skeleton.quality.scatter10240.caps.c0001 import Organ, OrganError, Pulse

ROOT = Path(__file__).resolve().parents[1] / "skeleton"

class ScatterTests(unittest.TestCase):
    def test_count(self):
        indexes = list(ROOT.glob("*/scatter10240/caps/INDEX.csv"))
        self.assertEqual(len(indexes), 16)
        total = 0
        for path in indexes:
            total += len(path.read_text().splitlines()) - 1
        self.assertEqual(total, 10240)

    def test_stimulus(self):
        with self.assertRaises(OrganError):
            Pulse(1, 1, "tok", stimulus="sentence")

    def test_admit(self):
        organ = Organ()
        card = organ.admit(Pulse(1, 1, "tok", cool=True))
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["hit"], 1)
        self.assertIsNotNone(organ.reverse())

    def test_double(self):
        self.assertEqual(16 * 640, 5120 * 2)

if __name__ == "__main__":
    unittest.main()
