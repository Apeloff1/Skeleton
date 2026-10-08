"""Fail-closed tests for PR #3482 seam proof_carrying_lifecycle."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.proof_carrying_lifecycle")


class TestProofCarryingLifecycle(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3482", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "proof-lifecycle")

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



    def test_promote_requires_hold(self):
        base = [mod.Proof.create(p, "claim-1", "d-"+p) for p in ("propose", "admit", "hold")]
        self.assertEqual(mod.advance(base).phase, "hold")
        promo = base + [mod.Proof.create("promote", "claim-1", "d-promote")]
        self.assertEqual(mod.advance(promo).phase, "promote")
        naked = [mod.Proof.create(p, "claim-1", "d-"+p) for p in ("propose", "admit", "promote")]
        with self.assertRaises(PermissionError):
            mod.advance(naked)

if __name__ == "__main__":
    unittest.main()
