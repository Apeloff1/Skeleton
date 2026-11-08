"""Adversarial operator objective evidence-family collapse tests."""
from __future__ import annotations

from dataclasses import replace
import unittest

import test_ai_webcrawler_dragon_atlas as fixtures
from skeleton.ai.webcrawler.dragon_campaign_stack import (
    ResearchObjective, compose_dragon_atlas,
    stress_test_evidence_families, verify_dragon_atlas_trace,
)


class SourceFamilyStressTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid",
        )
        self.f.setUp()
        self.mandate = self.f.mandate
        self.now = self.f.now + 3
        self.text = fixtures.research_text("family")
        self.altered = self.text + "\nAdditional editorial revision for manual source review."
        self.one = self.f.with_sources(
            ("https://example.com/a", self.text),
        )
        self.twins = self.f.with_sources(
            ("https://example.com/a", self.text),
            ("https://example.org/b", self.text),
        )
        self.edited = self.f.with_sources(
            ("https://example.com/a", self.text),
            ("https://example.org/b", self.altered),
        )

    def atlas(self, snapshot=None):
        return self.f.atlas(
            self.f.empty if snapshot is None else snapshot,
        )

    def stress(self, snapshot, atlas, **kwargs):
        return stress_test_evidence_families(
            self.mandate, snapshot, atlas.workbench.objectives,
            atlas.policies, atlas.retrieval, atlas.robustness,
            atlas.similarity, now=self.now, authorized=True, **kwargs,
        )

    def test_empty_research_does_not_fabricate_independent_sources(self):
        a = self.atlas()
        r = a.family_stress
        self.assertEqual(r.source_records_observed, 0)
        self.assertEqual(r.exact_content_families_observed, 0)
        self.assertEqual(r.possible_near_duplicate_clusters, 0)
        self.assertEqual(r.objectives[0].concern, "no_selected_source_evidence")
        self.assertFalse(r.independent_sources_certified)
        self.assertFalse(r.claim_correctness_verified)

    def test_one_capture_requires_separate_human_independence_review(self):
        a = self.atlas(self.one)
        row = a.family_stress.objectives[0]
        self.assertEqual(row.source_record_count, 1)
        self.assertEqual(row.exact_content_family_count, 1)
        self.assertEqual(row.possible_near_duplicate_cluster_count, 1)
        self.assertEqual(row.worst_observed_host_removal_cluster_count, 0)
        self.assertFalse(row.independent_evidence_attested)

    def test_exact_mirror_cannot_satisfy_two_independent_witnesses(self):
        a = self.atlas(self.twins)
        row = a.family_stress.objectives[0]
        if row.source_record_count == 2:
            self.assertEqual(row.exact_content_family_count, 1)
            self.assertEqual(row.possible_near_duplicate_cluster_count, 1)
            self.assertEqual(row.concern, "exact_content_reuse")
        self.assertFalse(row.independent_evidence_attested)

    def test_edited_mirrors_are_review_scenarios_not_proof(self):
        a = self.atlas(self.edited)
        row = a.family_stress.objectives[0]
        self.assertLessEqual(row.possible_near_duplicate_cluster_count,
                             row.exact_content_family_count)
        self.assertFalse(a.family_stress.independent_sources_certified)
        self.assertFalse(row.fact_verification_performed)

    def test_every_goal_count_is_bounded_by_selected_identities(self):
        a = self.atlas(self.edited)
        r = a.family_stress
        for row in r.objectives:
            self.assertLessEqual(row.possible_near_duplicate_cluster_count,
                                 row.exact_content_family_count)
            self.assertLessEqual(row.exact_content_family_count,
                                 row.source_record_count)
            self.assertGreaterEqual(row.hypothetical_target_shortfall, 0)

    def test_hypothetical_source_target_is_not_marked_as_attested(self):
        alternate = ResearchObjective(
            "second-goal", "What archive capture methodology is documented?",
            "method", "verification", .75, 1, 2, 3600,
            required_terms=("archive", "capture"),
        )
        a = compose_dragon_atlas(
            self.mandate, self.twins,
            objectives=(self.f.objective(), alternate),
            source_policies=self.f.policies(self.twins),
            policy_snapshot_authenticated=True,
            now=self.now, authorized=True,
        )
        rows = {x.objective_id: x for x in a.family_stress.objectives}
        self.assertEqual(len(rows), 2)
        row = rows["second-goal"]
        self.assertEqual(row.desired_attested_source_groups, 2)
        self.assertGreaterEqual(row.hypothetical_target_shortfall, 1)
        self.assertFalse(row.independent_evidence_attested)

    def test_zero_selected_passages_for_one_goal_does_not_erase_other(self):
        alternate = ResearchObjective(
            "unmatched-goal", "What does the zebra-only protocol report?",
            "method", "verification", .85, 1, 2, 3600,
            required_terms=("zebraonly",),
        )
        a = compose_dragon_atlas(
            self.mandate, self.one,
            objectives=(self.f.objective(), alternate),
            source_policies=self.f.policies(self.one),
            policy_snapshot_authenticated=True,
            now=self.now, authorized=True,
        )
        records = {x.objective_id: x for x in a.family_stress.objectives}
        self.assertGreater(records["archive-method"].source_record_count, 0)
        self.assertEqual(records["unmatched-goal"].source_record_count, 0)
        self.assertEqual(records["unmatched-goal"].hypothetical_target_shortfall, 2)

    def test_recompute_same_canonical_snapshot_yields_same_receipt(self):
        a = self.atlas(self.edited)
        self.assertEqual(self.stress(self.edited, a), a.family_stress)

    def test_trace_contains_26th_source_collapse_stage(self):
        a = self.atlas(self.edited)
        self.assertEqual(len(a.stages), 26)
        self.assertEqual(a.stages[-1].name,
                         "objective_evidence_family_collapse_stress")
        verify_dragon_atlas_trace(
            self.mandate, self.edited,
            a, now=self.now, authorized=True,
        )

    def test_tampered_family_stress_fails_even_if_digest_unchanged(self):
        a = self.atlas(self.one)
        altered = replace(a.family_stress, source_records_observed=42)
        with self.assertRaises(PermissionError):
            verify_dragon_atlas_trace(
                self.mandate, self.one,
                replace(a, family_stress=altered),
                now=self.now, authorized=True,
            )

    def test_stale_similarity_and_robustness_receipts_rejected(self):
        a = self.atlas(self.one)
        for changed in (
            {"similarity": replace(a.similarity, audit_digest="f" * 64)},
            {"robustness": replace(a.robustness, audit_digest="e" * 64)},
            {"retrieval": replace(a.retrieval, fusion_digest="d" * 64)},
        ):
            with self.subTest(changed=tuple(changed)):
                with self.assertRaises(PermissionError):
                    stress_test_evidence_families(
                        self.mandate, self.one,
                        a.workbench.objectives, a.policies,
                        changed.get("retrieval", a.retrieval),
                        changed.get("robustness", a.robustness),
                        changed.get("similarity", a.similarity),
                        now=self.now, authorized=True,
                    )

    def test_mismatched_policy_and_source_revision_rejected(self):
        a = self.atlas(self.one)
        stale = replace(a.policies, source_snapshot_digest="f" * 64)
        with self.assertRaises(PermissionError):
            stress_test_evidence_families(
                self.mandate, self.one,
                a.workbench.objectives, stale, a.retrieval,
                a.robustness, a.similarity,
                now=self.now, authorized=True,
            )

    def test_family_source_count_cap_is_enforced(self):
        a = self.atlas(self.one)
        with self.assertRaises(ValueError):
            self.stress(self.one, a, max_sources=0)
        with self.assertRaises(ValueError):
            self.stress(self.one, a, max_candidate_pairs=0)

    def test_withdrawn_sources_do_not_become_independent_evidence(self):
        a = compose_dragon_atlas(
            self.mandate, self.twins,
            objectives=(self.f.objective(),),
            source_policies=self.f.policies(self.twins, status="withdrawn"),
            policy_snapshot_authenticated=True,
            now=self.now, authorized=True,
        )
        self.assertEqual(a.family_stress.source_records_observed, 0)
        self.assertEqual(a.family_stress.possible_near_duplicate_clusters, 0)

    def test_same_source_cannot_bypass_withdrawal_using_forged_policy(self):
        a = self.atlas(self.one)
        altered = replace(a.policies, allowed_source_ids=(),
                          excluded_source_ids=())
        with self.assertRaises(PermissionError):
            stress_test_evidence_families(
                self.mandate, self.one,
                a.workbench.objectives, altered, a.retrieval,
                a.robustness, a.similarity, now=self.now, authorized=True,
            )

    def test_read_only_family_output_never_contains_source_bodies(self):
        a = self.atlas(self.edited)
        r = a.family_stress
        self.assertFalse(r.source_text_exported)
        self.assertFalse(r.model_or_network_invoked)
        self.assertFalse(r.independent_sources_certified)
        self.assertFalse(r.claim_correctness_verified)
        self.assertTrue(r.human_review_required)
        self.assertTrue(all(not hasattr(x, "body") for x in r.objectives))


if __name__ == "__main__":
    unittest.main()
