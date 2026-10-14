"""Fail-closed tests for PR #3480 seam outcome_mass_gate."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.outcome_mass_gate")


class TestOutcomeMassGate(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3480", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "outcome-mass")

    def test_rejects_prose(self):
        with self.assertRaises(PermissionError):
            mod.card(True, stored_prose=1)

    def test_pointer_bound(self):
        with self.assertRaises(ValueError):
            mod._id("has\nnewline", "x")
        with self.assertRaises(ValueError):
            mod._u(-1, "n")
        with self.assertRaises(ValueError):
            mod._u(True, "n")



    def test_clip(self):
        ok = mod.admit(mod.Outcome.create("proj", True, 105, 100, "ev"))
        self.assertTrue(ok.admitted)
        snow = mod.admit(mod.Outcome.create("proj", True, 200, 100, "ev"))
        self.assertFalse(snow.admitted)
        self.assertEqual(snow.reason, "mass-snowball")
        self.assertEqual(snow.clipped_mass, 110)

if __name__ == "__main__":
    unittest.main()
