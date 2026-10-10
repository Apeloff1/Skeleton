"""Fail-closed tests for PR #3486 seam inference_boundary_witness."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.inference_boundary_witness")


class TestInferenceBoundaryWitness(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3486", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "inference-boundary")

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



    def test_accept_until_mismatch(self):
        span = mod.TokenSpan.create("prompt-hash", (1, 2, 3), 4)
        hit = mod.accept_until_mismatch(span, [9, 9, 9], [9, 9, 9])
        self.assertLess(hit.mismatch_at, 0)
        miss = mod.accept_until_mismatch(span, [9, 8, 7], [9, 1, 7])
        self.assertEqual(miss.accepted, 1)
        self.assertEqual(miss.mismatch_at, 1)
        card = mod.exit_card(span, miss)
        self.assertFalse(card["hit"])

if __name__ == "__main__":
    unittest.main()
