"""Fail-closed tests for PR #3484 seam context_provenance_chain."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.context_provenance_chain")


class TestContextProvenanceChain(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3484", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "context-provenance")

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



    def test_ncap_and_bind(self):
        clauses = [mod.PointerClause.create("https://example.com/%d" % i, "2026-10", i) for i in range(3)]
        root = mod.bind(clauses)
        self.assertEqual(root.n, 3)
        self.assertEqual(mod.exit_card(root)["stored_prose"], 0)
        over = [mod.PointerClause.create("https://example.com/%d" % i, "2026-10", i) for i in range(9)]
        with self.assertRaises(PermissionError):
            mod.bind(over)

if __name__ == "__main__":
    unittest.main()
