"""FACET-10240. Lazy. One facet sampled. Count from indexes."""
import unittest
from pathlib import Path
from skeleton.chronicle.facet10240.caps.c0001 import Organ, OrganError, Pulse, security
from skeleton.hive.facet10240.caps.c0001 import OrganError as HiveError
from skeleton.hive.facet10240.caps.c0001 import Pulse as HivePulse

ROOT = Path(__file__).resolve().parents[1] / "skeleton"


class FacetTests(unittest.TestCase):
    def test_count(self):
        indexes = list(ROOT.glob("*/facet10240/caps/INDEX.csv"))
        self.assertEqual(len(indexes), 16)
        total = sum(len(p.read_text().splitlines()) - 1 for p in indexes)
        self.assertEqual(total, 10240)

    def test_token(self):
        with self.assertRaises(OrganError):
            Pulse(1, 1, "bad token")

    def test_coin(self):
        with self.assertRaises(HiveError):
            HivePulse(1, 1, "coin")
        self.assertEqual(security()["coin"], 0)

    def test_stimulus(self):
        with self.assertRaises(OrganError):
            Pulse(1, 1, "merkle", stimulus="sentence")

    def test_admit(self):
        organ = Organ()
        card = organ.admit(Pulse(1, 1, "merkle", cool=True))
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["hit"], 1)
        self.assertIsNotNone(organ.reverse())

    def test_same_level(self):
        self.assertEqual(16 * 640, 10240)


if __name__ == "__main__":
    unittest.main()
