"""Fail-closed tests for PR #3479 seam knowledge_context_unify."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.knowledge_context_unify")


class TestKnowledgeContextUnify(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3479", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "knowledge-unify")

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



    def test_weight_sum(self):
        shards = [
            mod.Shard.create("web", "https://example.com/a", 400000),
            mod.Shard.create("memory", "github.com/Apeloff1/Skeleton", 600000),
        ]
        bound = mod.unify(shards)
        self.assertEqual(bound.weight_ppm, 1000000)
        with self.assertRaises(PermissionError):
            mod.unify(shards[:1])

if __name__ == "__main__":
    unittest.main()
