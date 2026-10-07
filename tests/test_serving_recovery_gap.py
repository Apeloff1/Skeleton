"""Fail-closed tests for PR #3475 seam serving_recovery_gap."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.serving_recovery_gap")


class TestServingRecoveryGap(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3475", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "serving-recovery")

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



    def test_close_action(self):
        gap = mod.Gap.create("stale-lease", "sess-1", 15)
        closed = mod.close_gap(gap, 16)
        self.assertEqual(closed.action, "revoke-lease")
        with self.assertRaises(PermissionError):
            mod.close_gap(gap, 1)

if __name__ == "__main__":
    unittest.main()
