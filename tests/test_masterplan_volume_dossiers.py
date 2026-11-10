"""Negative tests for source-bound completionist masterplan dossiers."""
from __future__ import annotations

import unittest

from scripts.check_masterplan_volume_dossiers import (
    DOCS, ROOT, _load, audit, inspect_dossier,
)


class TestMasterplanVolumeDossiers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master, cls.sha = _load(ROOT, "machine/ai_master_plan.json")
        cls.roadmap, _ = _load(ROOT, "machine/ai_100_large_delivery_milestones.json")
        cls.volume = cls.master["volumes"][250]
        cls.milestone = next(
            m for m in cls.roadmap["milestones"]
            if any(v["id"] == cls.volume["key"] for v in m["volumes"])
        )
        cls.original = (ROOT / DOCS / "VOL-250.md").read_text(encoding="utf-8")

    def inspect(self, content):
        inspect_dossier(content, self.volume, self.milestone, self.sha)

    def test_421_dossiers_and_100_bundles_are_integral(self):
        result = audit()
        self.assertEqual(result["structural_dossiers_verified"], 421)
        self.assertEqual(result["milestone_bindings_verified"], 100)
        self.assertEqual(result["mandatory_layers_each"], 14)
        self.assertFalse(result["product_or_release_approval"])
        self.assertEqual(result["independent_milestone_qualification_proven_here"], 0)

    def test_pinned_example_is_valid(self):
        self.inspect(self.original)

    def test_missing_requirement_is_rejected(self):
        changed = self.original.replace(
            "- Every causal edge records evidence/method/assumptions.",
            "- Causal details are optional.", 1
        )
        with self.assertRaisesRegex(ValueError, "missing requirements"):
            self.inspect(changed)

    def test_missing_declared_test_is_rejected(self):
        changed = self.original.replace(
            "- planned:skeleton/testing/test_causal_knowledge.py",
            "- planned:example/undeclared.py", 1
        )
        with self.assertRaisesRegex(ValueError, "missing tests"):
            self.inspect(changed)

    def test_missing_layer_is_rejected(self):
        changed = self.original.replace(
            "### L06 — Failure and recovery", "### Unscoped failure",
            1
        )
        with self.assertRaisesRegex(ValueError, "L00-L13"):
            self.inspect(changed)

    def test_duplicate_layer_is_rejected(self):
        changed = self.original.replace(
            "### L06 — Failure and recovery",
            "### L06 — Failure and recovery\n### L06 — counterfeit duplicate",
            1
        )
        with self.assertRaisesRegex(ValueError, "L00-L13"):
            self.inspect(changed)

    def test_retarget_to_different_source_is_rejected(self):
        changed = self.original.replace(self.sha, "0" * 40, 1)
        with self.assertRaisesRegex(ValueError, "source pin"):
            self.inspect(changed)

    def test_forged_qualification_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "self-issued"):
            self.inspect(self.original + "\nqualification=PASSED\n")

    def test_missing_accountability_is_rejected(self):
        changed = self.original.replace("ACC-VOL-250", "ACC-VOL-251", 1)
        with self.assertRaisesRegex(ValueError, "accountability"):
            self.inspect(changed)

    def test_wrong_milestone_receipt_is_rejected(self):
        changed = self.original.replace(
            "milestone=MDM-058", "milestone=MDM-057", 1
        )
        with self.assertRaisesRegex(ValueError, "milestone receipt"):
            self.inspect(changed)

    def test_planned_paths_are_explicitly_unqualified(self):
        self.assertIn("planned:skeleton/testing/test_causal_knowledge.py", self.original)
        self.assertIn("qualification=UNVERIFIED_BY_THIS_DOSSIER", self.original)


if __name__ == "__main__":
    unittest.main()
