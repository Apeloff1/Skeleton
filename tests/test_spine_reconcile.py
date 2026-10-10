"""Fail-closed tests for PR #3477 seam spine_reconcile."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.spine_reconcile")


class TestSpineReconcile(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3477", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "spine-reconcile")

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



    def test_four_planes(self):
        nodes = [mod.SpineNode.create(p, "d-"+p) for p in ("crawl", "retrieve", "context", "generate")]
        spine = mod.reconcile(nodes)
        self.assertEqual(mod.exit_card(spine)["planes"], 4)
        with self.assertRaises(PermissionError):
            mod.reconcile(nodes[:-1])

if __name__ == "__main__":
    unittest.main()
