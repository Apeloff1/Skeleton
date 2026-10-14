"""Fail-closed tests for PR #3487 seam admission_window_binder."""
from __future__ import annotations

import importlib
import unittest


mod = importlib.import_module("skeleton.ai.pr_seams.admission_window_binder")


class TestAdmissionWindowBinder(unittest.TestCase):
    def test_card_law(self):
        self.assertEqual(mod.LAW, "stored_prose=0")
        self.assertIn("/pull/3487", mod.CITATION)
        sample = mod.card(True, probe=1)
        self.assertEqual(sample["stored_prose"], 0)
        self.assertTrue(sample["hit"])
        self.assertEqual(sample["kind"], "admission-window")

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



    def test_bind_and_reject_foreign(self):
        w = mod.Window.create("wf", "step", 2, 10, 100, 40)
        bids = [mod.Bid.create(w, p, i, 8, "ev-"+p) for i, p in enumerate(mod.PARTICIPANTS)]
        grant = mod.bind(w, bids, 20)
        self.assertEqual(grant.admitted_mass, 32)
        self.assertEqual(grant.residual, 8)
        card = mod.exit_card(w, grant)
        self.assertEqual(card["stored_prose"], 0)
        other = mod.Window.create("wf", "step", 3, 10, 100, 40)
        foreign = mod.Bid.create(other, "schedule", 0, 8, "ev-x")
        with self.assertRaises(PermissionError):
            mod.bind(w, list(bids[:-1]) + [foreign], 20)

if __name__ == "__main__":
    unittest.main()
