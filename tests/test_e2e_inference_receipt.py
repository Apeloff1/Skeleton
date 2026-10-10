"""Fail-closed tests for PR #3483 seam e2e_inference_receipt."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.e2e_inference_receipt")


class TestE2EInferenceReceipt(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3483", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "e2e-inference")

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



    def test_close_sums(self):
        names = ("encode", "prefill", "decode", "verify", "emit")
        stages = [mod.Stage.create(n, "d-"+n, 10) for n in names]
        rec = mod.close(stages)
        self.assertEqual(rec.total_ns, 50)
        with self.assertRaises(PermissionError):
            mod.close(stages[:-1])

if __name__ == "__main__":
    unittest.main()
