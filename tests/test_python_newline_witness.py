"""Fail-closed tests for PR #3481 seam python_newline_witness."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.python_newline_witness")


class TestPythonNewlineWitness(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3481", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "syntax-witness")

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



    def test_repair_cr(self):
        raw = "def f():\r    return 1"
        found = mod.witness(raw)
        self.assertTrue(found.corrupt)
        fixed = mod.repair_newlines(raw)
        after = mod.witness(fixed)
        self.assertFalse(after.corrupt)
        self.assertIn("\n", fixed)

if __name__ == "__main__":
    unittest.main()
