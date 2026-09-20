"""GB-24 accept tests."""

from __future__ import annotations

import unittest

from skeleton.circulation import CirculationEngine, capabilities, shunt_fever
from skeleton.circulation.verify import run_all


class TestShunt(unittest.TestCase):
    def test_hot_drops(self) -> None:
        self.assertEqual(shunt_fever(1.2)["dropped"], 1)

    def test_cool_keeps(self) -> None:
        cool = shunt_fever(1.2, cool=True)
        self.assertEqual(cool["dropped"], 0)
        self.assertEqual(cool["heat_out"], 0.0)

    def test_warm_keeps(self) -> None:
        self.assertEqual(shunt_fever(0.5)["dropped"], 0)


class TestCaps(unittest.TestCase):
    def test_engine(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["owner"], "circulation")
        self.assertEqual(cap["contract"]["cool_drops"], 0)
        snap = CirculationEngine().snapshot()
        self.assertEqual(snap["hit"], 1)
        self.assertEqual(snap["stored_prose"], 0)
        self.assertEqual(run_all()["failed"], [])


if __name__ == "__main__":
    unittest.main()
