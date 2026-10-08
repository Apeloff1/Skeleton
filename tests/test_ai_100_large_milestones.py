"""Regression coverage for the 100 large milestone execution overlay."""
from __future__ import annotations

import copy
import unittest

from scripts.check_ai_100_large_milestones import (
    FILES, ROOT, load_json, verify, report, run,
)


class TestLargeMilestoneExecution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roadmap, _ = load_json(ROOT / "machine/ai_100_large_delivery_milestones.json")
        cls.sources = {}
        cls.shas = {}
        for key, path in FILES.items():
            cls.sources[key], cls.shas[key] = load_json(ROOT / path)

    def validate(self, roadmap=None, *, source=None, index=None, shas=None):
        verify(
            self.roadmap if roadmap is None else roadmap,
            self.sources["master_plan"] if source is None else source,
            self.sources["advanced_ladder"],
            self.sources["accountability_index"] if index is None else index,
            self.shas if shas is None else shas,
        )

    def test_full_100_milestone_contract_is_valid(self):
        self.validate()
        self.assertEqual(len(self.roadmap["milestones"]), 100)
        self.assertEqual(len(self.roadmap["delivery_trains"]), 10)

    def test_all_421_original_volumes_covered_once(self):
        refs = [v["id"] for m in self.roadmap["milestones"] for v in m["volumes"]]
        self.assertEqual(refs, [f"VOL-{i:03d}" for i in range(421)])
        self.assertEqual(len(refs), len(set(refs)))

    def test_each_major_milestone_contains_four_or_five_volumes(self):
        counts = [len(m["volumes"]) for m in self.roadmap["milestones"]]
        self.assertEqual(counts.count(5), 21)
        self.assertEqual(counts.count(4), 79)

    def test_every_volume_has_source_bound_tests_and_target(self):
        for m in self.roadmap["milestones"]:
            for v in m["volumes"]:
                with self.subTest(milestone=m["id"], volume=v["id"]):
                    self.assertTrue(v["acceptance_tests"])
                    self.assertTrue(v["contract_targets"])
                    self.assertTrue(v["required_outcome"])
                    self.assertTrue(v["accountability"])

    def test_no_unsupported_milestone_signatures(self):
        self.assertTrue(all(
            m["status"] == "unverified" and m["completion_signoff"] is None
            for m in self.roadmap["milestones"]
        ))

    def test_report_keeps_completion_separate_from_source_navigation(self):
        state = run()
        self.assertEqual(state["milestones_defined"], 100)
        self.assertEqual(state["volumes_covered"], 421)
        self.assertEqual(state["independently_qualified_milestones"], 0)

    def test_source_signed_subgroup_cannot_auto_promote_milestone(self):
        mock = copy.deepcopy(self.sources["accountability_index"])
        refs = [v["id"] for v in self.roadmap["milestones"][0]["volumes"]]
        mock["fast_sets"]["fully_complete"] = refs
        state = report(self.roadmap, mock)
        self.assertEqual(state["all_source_signed_groups"], 1)
        self.assertEqual(state["independently_qualified_milestones"], 0)

    def test_duplicate_volume_claim_fails(self):
        tampered = copy.deepcopy(self.roadmap)
        tampered["milestones"][1]["volumes"][0] = copy.deepcopy(
            tampered["milestones"][0]["volumes"][0]
        )
        with self.assertRaisesRegex(ValueError, "fabricated/missing"):
            self.validate(tampered)

    def test_missing_milestone_fails(self):
        tampered = copy.deepcopy(self.roadmap)
        tampered["milestones"].pop()
        with self.assertRaisesRegex(ValueError, "100 milestone"):
            self.validate(tampered)

    def test_status_forgery_fails(self):
        tampered = copy.deepcopy(self.roadmap)
        tampered["milestones"][1]["status"] = "complete"
        with self.assertRaisesRegex(ValueError, "unearned completion"):
            self.validate(tampered)

    def test_fake_signoff_fails(self):
        tampered = copy.deepcopy(self.roadmap)
        tampered["milestones"][0]["completion_signoff"] = {
            "verified_at": "2026-10-08T00:00:00Z",
        }
        with self.assertRaisesRegex(ValueError, "unearned completion"):
            self.validate(tampered)

    def test_removed_failure_gate_fails(self):
        tampered = copy.deepcopy(self.roadmap)
        tampered["milestones"][0]["exit_gates"].pop()
        with self.assertRaisesRegex(ValueError, "noncompensable gate"):
            self.validate(tampered)

    def test_fabricated_test_binding_fails(self):
        tampered = copy.deepcopy(self.roadmap)
        tampered["milestones"][17]["volumes"][0]["acceptance_tests"] = ["tests/fake.py"]
        with self.assertRaisesRegex(ValueError, "fabricated/missing"):
            self.validate(tampered)

    def test_canonical_volume_title_drift_fails(self):
        source = copy.deepcopy(self.sources["master_plan"])
        source["volumes"][20]["title"] = "changed identity"
        with self.assertRaises(ValueError):
            self.validate(source=source)

    def test_source_sha_pin_drift_fails(self):
        shas = dict(self.shas)
        shas["master_plan"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "stale source"):
            self.validate(shas=shas)

    def test_stale_accountability_index_fails(self):
        index = copy.deepcopy(self.sources["accountability_index"])
        index["sources"][FILES["accountability"]]["git_blob_sha"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "stale navigation"):
            self.validate(index=index)

    def test_claimed_different_authority_fails(self):
        changed = copy.deepcopy(self.roadmap)
        changed["qualification"]["evidence_source"] = "untrusted-proposal.json"
        with self.assertRaisesRegex(ValueError, "noncanonical completion"):
            self.validate(changed)

    def test_invalid_signed_set_fails(self):
        index = copy.deepcopy(self.sources["accountability_index"])
        index["fast_sets"]["fully_complete"] = ["VOL-000", "VOL-000"]
        with self.assertRaisesRegex(ValueError, "signed volume"):
            report(self.roadmap, index)

    def test_unknown_signed_volume_fails(self):
        index = copy.deepcopy(self.sources["accountability_index"])
        index["fast_sets"]["fully_complete"] = ["VOL-999"]
        with self.assertRaisesRegex(ValueError, "signed volume"):
            report(self.roadmap, index)

    def test_original_masterplan_frozen_at_420(self):
        self.assertTrue(self.sources["master_plan"]["breadth_freeze"]["enabled"])
        self.assertEqual(
            self.sources["master_plan"]["breadth_freeze"]["last_top_level_volume"], 420
        )


if __name__ == "__main__":
    unittest.main()
