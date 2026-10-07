"""Fail-closed tests for PR #3485 seam runtime_integration_seal."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.runtime_integration_seal")


class TestRuntimeIntegrationSeal(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3485", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "runtime-integration")

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



    def test_seal_requires_full_plane(self):
        pins = [mod.PlanePin.create(name, "dig-"+name, 4) for name in mod.REQUIRED]
        bound = mod.seal(pins)
        self.assertEqual(bound.generation, 4)
        self.assertEqual(len(bound.pin_ids), 5)
        with self.assertRaises(PermissionError):
            mod.seal(pins[:-1])

if __name__ == "__main__":
    unittest.main()
