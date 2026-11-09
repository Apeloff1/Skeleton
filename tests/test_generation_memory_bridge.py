"""Fail-closed tests for PR #3478 seam generation_memory_bridge."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.generation_memory_bridge")


class TestGenerationMemoryBridge(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3478", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "memory-bridge")

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



    def test_reversible_bind(self):
        ev = mod.Evidence.create("gen-1", "digest", True)
        slot = mod.bind("proj", ev)
        self.assertTrue(slot.reversible)
        self.assertTrue(mod.reverse(slot)["reversed"])
        bad = mod.Evidence.create("gen-1", "digest", False)
        with self.assertRaises(PermissionError):
            mod.bind("proj", bad)

if __name__ == "__main__":
    unittest.main()
