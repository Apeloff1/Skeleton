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



    def test_gap_in_ordinals_fails_closed(self):
        clauses = (
            mod.PointerClause.create("https://example.com/0", "2026-10", 0),
            mod.PointerClause.create("https://example.com/2", "2026-10", 2),
        )
        with self.assertRaisesRegex(PermissionError, "ordinal collision or gap"):
            mod.bind(clauses)

    def test_mutated_pointer_content_and_identity_rejected(self):
        from dataclasses import replace
        original = mod.PointerClause.create("https://example.com/a", "2026-10", 0)
        for changed in (
            replace(original, url="https://example.com/other"),
            replace(original, era="2020-01"),
            replace(original, clause_id="0" * 64),
        ):
            with self.assertRaisesRegex(PermissionError, "identity mismatch"):
                mod.bind((changed,))

    def test_malformed_pointer_types_and_url_whitespace_rejected(self):
        with self.assertRaises(TypeError):
            mod.bind(("pointer",))
        with self.assertRaises(ValueError):
            mod.PointerClause.create("https://example.com/a\\tb", "2026-10", 0)

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
