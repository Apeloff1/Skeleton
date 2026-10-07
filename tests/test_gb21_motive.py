"""GB-21 accept tests. Isolated. No torch. No network. No spine import."""

from __future__ import annotations

import sys
import unittest

from skeleton.motive import (
    HEART_H0,
    MotiveEngine,
    capabilities,
    heart,
    map_s_s_is_s,
    omega_sigma_iso_id,
    smash,
    sphere,
    suspend,
)
from skeleton.motive.verify import run_all


class TestSphereLaws(unittest.TestCase):
    def test_omega_sigma_id(self) -> None:
        self.assertTrue(omega_sigma_iso_id(sphere()))

    def test_map_ss(self) -> None:
        self.assertTrue(map_s_s_is_s())

    def test_heart(self) -> None:
        self.assertEqual(HEART_H0, 1)
        self.assertEqual(heart(), 1)

    def test_smash_suspend(self) -> None:
        s = sphere()
        self.assertIn("*", smash(s, s).points)
        self.assertTrue(suspend(s).name.startswith("smash"))


class TestCapsEngine(unittest.TestCase):
    def test_capabilities(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["owner"], "motive")
        self.assertEqual(cap["contract"]["heart_h0"], 1)
        self.assertEqual(cap["contract"]["spine_bus"], "thin")
        self.assertEqual(cap["security"]["network"], 0)

    def test_no_spine_import(self) -> None:
        self.assertNotIn("skeleton.spine", sys.modules)

    def test_engine_and_verify(self) -> None:
        snap = MotiveEngine().snapshot()
        self.assertEqual(snap["hit"], 1)
        self.assertEqual(snap["stored_prose"], 0)
        self.assertEqual(snap["H0"], 1)
        self.assertEqual(run_all()["failed"], [])


if __name__ == "__main__":
    unittest.main()
