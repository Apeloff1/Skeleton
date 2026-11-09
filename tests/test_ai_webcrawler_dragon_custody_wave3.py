"""Third-wave Dragon Atlas capture and research custody regression coverage.

Exercises typed source-only postures plus the integrated read-only forensic
chain. No real HTTP, database writes, worker creation or policy promotion.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import copy
import json
import unittest

import test_ai_webcrawler_dragon_atlas as fixtures
from skeleton.ai.webcrawler.dragon_campaign_stack import ResearchObjective
from skeleton.ai.webcrawler.dragon_campaign_stack.forensics import (
    audit_capture_provenance, inspect_objective_grounding,
    inspect_reference_concentration, inspect_consent_horizon,
    compose_atlas_forensics, verify_atlas_forensics,
    bind_selected_frames, compile_forensic_review_queue,
    scan_text_security, measure_anchor_geometry, analyze_source_reuse,
    analyze_objective_resilience, inspect_boilerplate, inspect_capture_age,
)


class DragonCustodyWave3Tests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid",
        )
        self.f.setUp()
        self.now = self.f.now + 3
        text = fixtures.research_text("custody")
        self.single = self.f.with_sources(("https://example.com/a", text))
        self.duo = self.f.with_sources(
            ("https://example.com/a", text),
            ("https://example.org/b", text),
        )

    def current(self, snapshot):
        atlas = self.f.atlas(snapshot)
        frames = bind_selected_frames(
            self.f.mandate, snapshot, atlas.policies, atlas.retrieval,
            now=self.now, authorized=True,
        )
        return atlas, frames

    def forensics(self, snapshot):
        atlas, frames = self.current(snapshot)
        report = compose_atlas_forensics(
            self.f.mandate, snapshot, atlas,
            now=self.now, authorized=True,
        )
        return atlas, frames, report

    def test_empty_campaign_has_typed_no_source_provenance(self):
        _, frames = self.current(self.f.empty)
        posture = audit_capture_provenance(
            self.f.mandate, self.f.empty, frames,
            now=self.now, authorized=True,
        )
        self.assertEqual(posture.findings, ())
        self.assertTrue(posture.identity_violations_rejected)
        self.assertFalse(posture.content_rights_certified)

    def test_canonical_capture_binding_is_verified_without_rights_grant(self):
        atlas, frames, report = self.forensics(self.single)
        p = report.provenance
        self.assertTrue(p.findings)
        self.assertEqual(p.source_snapshot_digest, atlas.source_snapshot_digest)
        self.assertEqual(p.frame_set_digest, frames.frame_set_digest)
        self.assertTrue(all(x.source_identity_verified for x in p.findings))
        self.assertFalse(p.content_rights_certified)
        self.assertFalse(p.source_text_exported)

    def test_raw_body_absence_is_visible_not_silently_replayable(self):
        _, _, report = self.forensics(self.single)
        self.assertEqual(report.provenance.replayable_raw_body_count, 0)
        self.assertTrue(all("raw_body_not_retained" in x.flags
                            for x in report.provenance.findings))
        self.assertTrue(any(x.reason == "capture_provenance:raw_body_not_retained"
                            for x in report.reviews.tasks))

    def test_provenance_does_not_export_page_body(self):
        _, _, report = self.forensics(self.single)
        raw = json.dumps(asdict(report))
        self.assertNotIn(fixtures.research_text("custody"), raw)
        self.assertFalse(report.provenance.source_text_exported)
        self.assertFalse(report.reference_concentration.citation_truth_verified)

    def test_selected_source_anchor_hash_tamper_rejected(self):
        atlas, frames = self.current(self.single)
        self.assertTrue(frames.frames)
        old = frames.frames[0].anchor
        bad = replace(old, source_hash="a" * 64)
        forged = replace(frames, frames=(replace(frames.frames[0], anchor=bad),)
                         + frames.frames[1:])
        with self.assertRaises(PermissionError):
            audit_capture_provenance(
                self.f.mandate, self.single, forged,
                now=self.now, authorized=True,
            )

    def test_current_source_hash_is_integrity_critical(self):
        atlas, frames = self.current(self.single)
        modified = copy.deepcopy(self.single)
        key = next(iter(modified["sources"]))
        modified["sources"][key]["provenance"]["content_hash"] = "b" * 64
        with self.assertRaises(Exception):
            audit_capture_provenance(
                self.f.mandate, modified, frames,
                now=self.now, authorized=True,
            )

    def test_expired_consent_denied_even_when_frame_snapshot_old(self):
        _, frames = self.current(self.single)
        with self.assertRaises(PermissionError):
            audit_capture_provenance(
                self.f.mandate, self.single, frames,
                now=self.f.now + 3601, authorized=True,
            )

    def test_unauthorized_provenance_inspection_denied(self):
        _, frames = self.current(self.single)
        with self.assertRaises(PermissionError):
            audit_capture_provenance(
                self.f.mandate, self.single, frames,
                now=self.now, authorized=False,
            )

    def test_operator_objective_matching_is_lexical_only(self):
        atlas, frames, report = self.forensics(self.single)
        rows = report.grounding.objectives
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].objective_id, "archive-method")
        self.assertGreater(rows[0].selected_passages, 0)
        self.assertFalse(rows[0].lexical_match_proves_claim)
        self.assertFalse(report.grounding.factual_answerability_certified)
        self.assertEqual(report.grounding.objective_plan_digest,
                         atlas.workbench.objectives.plan_digest)

    def test_unselected_operator_objective_has_missing_evidence_hold(self):
        a, frames = self.current(self.single)
        # Use a second operator objective in the real Atlas, never synthesize
        # a question from untrusted source text.
        goal = ResearchObjective(
            "another-goal", "How was a zebra-only protocol implemented?",
            "implementation", "verification", .9, 1, 2, 3600,
            required_terms=("zebraonly",),
        )
        from skeleton.ai.webcrawler.dragon_campaign_stack import (
            compose_dragon_atlas,
        )
        atlas = compose_dragon_atlas(
            self.f.mandate, self.single,
            objectives=(self.f.objective(), goal),
            source_policies=self.f.policies(self.single),
            policy_snapshot_authenticated=True,
            now=self.f.now + 2, authorized=True,
        )
        selected = bind_selected_frames(
            self.f.mandate, self.single, atlas.policies, atlas.retrieval,
            now=self.now, authorized=True,
        )
        result = inspect_objective_grounding(
            selected, atlas.workbench.objectives,
        )
        self.assertIn("another-goal", result.missing_or_weak_objectives)
        other = next(x for x in result.objectives if x.objective_id == "another-goal")
        self.assertEqual(other.selected_passages, 0)
        self.assertTrue(other.missing_evidence_review)

    def test_unmandated_objective_anchor_fails_closed(self):
        atlas, frames = self.current(self.single)
        if not frames.frames:
            self.skipTest("fixture retrieval did not select a passage")
        original = frames.frames[0]
        modified = replace(original, anchor=replace(
            original.anchor, objective_ids=("foreign-operator",),
        ))
        forged = replace(frames, frames=(modified,) + frames.frames[1:])
        with self.assertRaises(PermissionError):
            inspect_objective_grounding(forged, atlas.workbench.objectives)

    def test_blocked_operator_term_is_reported_as_constraint_violation(self):
        atlas, frames = self.current(self.single)
        objective = replace(
            atlas.workbench.objectives.objectives[0],
            blocked_terms=("blockedterm",),
        )
        plan = replace(atlas.workbench.objectives, objectives=(objective,))
        original = frames.frames[0]
        selected = replace(frames, frames=(replace(
            original, text=original.text + " blockedterm",
        ),) + frames.frames[1:])
        result = inspect_objective_grounding(selected, plan)
        self.assertEqual(result.prohibited_objectives, ("archive-method",))
        self.assertTrue(result.objectives[0].prohibited_term_passages)

    def test_repeated_passages_not_multiple_corroboration(self):
        _, frames = self.current(self.duo)
        report = inspect_reference_concentration(frames)
        self.assertEqual(report.total_anchor_records, len(frames.frames))
        self.assertLessEqual(report.unique_passage_text_hashes,
                             report.total_anchor_records)
        self.assertFalse(report.source_independence_confirmed)
        self.assertFalse(report.citation_truth_verified)

    def test_multi_objective_reuse_is_metadata_hold(self):
        _, frames = self.current(self.single)
        original = frames.frames[0]
        duplicated_goal = replace(original.anchor, objective_ids=(
            "archive-method", "second-goal",
        ))
        simulated = replace(frames, frames=(replace(
            original, anchor=duplicated_goal,
        ),) + frames.frames[1:])
        result = inspect_reference_concentration(simulated)
        self.assertEqual(result.cross_objective_reused_source_count, 1)
        self.assertTrue(result.held_source_ids)

    def test_no_selection_is_not_single_source_concentration(self):
        _, frames = self.current(self.f.empty)
        result = inspect_reference_concentration(frames)
        self.assertEqual(result.total_anchor_records, 0)
        self.assertFalse(result.single_source_concentration)

    def test_consent_horizon_never_authorizes_future_acquisition(self):
        _, frames = self.current(self.single)
        horizon = inspect_consent_horizon(
            self.f.mandate, frames, now=self.now, authorized=True,
        )
        self.assertEqual(horizon.warning, "current_consent_window")
        self.assertTrue(horizon.requires_fresh_policy_for_future_use)
        self.assertFalse(horizon.source_policy_expiry_known)
        self.assertFalse(horizon.recrawl_authorized)
        self.assertFalse(horizon.knowledge_promotion_authorized)

    def test_consent_horizon_warning_is_pure_and_bounded(self):
        _, frames = self.current(self.single)
        horizon = inspect_consent_horizon(
            self.f.mandate, frames, now=self.f.now + 3550,
            authorized=True, warn_before_seconds=90,
        )
        self.assertEqual(horizon.warning, "renewal_review_due")
        self.assertLessEqual(horizon.consent_seconds_remaining, 90)
        with self.assertRaises(ValueError):
            inspect_consent_horizon(
                self.f.mandate, frames, now=self.now, authorized=True,
                warn_before_seconds=0,
            )

    def test_expired_horizon_denied(self):
        _, frames = self.current(self.single)
        with self.assertRaises(PermissionError):
            inspect_consent_horizon(
                self.f.mandate, frames, now=self.f.now + 3600,
                authorized=True,
            )

    def test_seventeen_stage_source_replay_and_chain_verification(self):
        atlas, frames, report = self.forensics(self.single)
        self.assertEqual(len(report.stages), 26)
        self.assertEqual(report.stages[12].name,
                         "canonical_capture_provenance_posture")
        self.assertEqual(report.stages[13].name, "operator_objective_grounding")
        self.assertEqual(report.stages[14].name, "selected_reference_concentration")
        self.assertEqual(report.stages[15].name, "mandate_consent_horizon")
        self.assertEqual(report.stages[16].name, "reverse_source_objective_usage")
        self.assertEqual(report.stages[17].name, "policy_bound_research_deficit_matrix")
        self.assertEqual(report.stages[18].name, "untrusted_context_resource_budget")
        self.assertEqual(report.stages[-1].name, "review_only_forensic_queue")
        verify_atlas_forensics(
            self.f.mandate, self.single, atlas, report,
            now=self.now, authorized=True,
        )

    def test_old_eight_stage_shape_cannot_impersonate_new_receipt_chain(self):
        atlas, frames, report = self.forensics(self.single)
        removed = replace(report, stages=report.stages[:8])
        with self.assertRaises(PermissionError):
            verify_atlas_forensics(
                self.f.mandate, self.single, atlas, removed,
                now=self.now, authorized=True,
            )

    def test_forged_provenance_detail_does_not_pass_replay(self):
        atlas, frames, report = self.forensics(self.single)
        forged = replace(report, provenance=replace(
            report.provenance, held_source_ids=(),
        ))
        with self.assertRaises(PermissionError):
            verify_atlas_forensics(
                self.f.mandate, self.single, atlas, forged,
                now=self.now, authorized=True,
            )

    def test_forged_grounding_detail_does_not_pass_replay(self):
        atlas, frames, report = self.forensics(self.single)
        forged = replace(report, grounding=replace(
            report.grounding, missing_or_weak_objectives=("foreign",),
        ))
        with self.assertRaises(PermissionError):
            verify_atlas_forensics(
                self.f.mandate, self.single, atlas, forged,
                now=self.now, authorized=True,
            )

    def test_reviews_require_exact_current_frame_set(self):
        atlas, frames, report = self.forensics(self.single)
        synthetic = replace(report.provenance, frame_set_digest="d" * 64)
        with self.assertRaises(PermissionError):
            compile_forensic_review_queue(
                frames, scan_text_security(frames),
                measure_anchor_geometry(frames),
                analyze_source_reuse(frames, atlas.similarity),
                analyze_objective_resilience(frames, atlas.workbench.objectives,
                    analyze_source_reuse(frames, atlas.similarity)),
                inspect_boilerplate(frames),
                inspect_capture_age(self.f.mandate, self.single, frames,
                    atlas.workbench.objectives, now=self.now, authorized=True),
                provenance=synthetic,
            )

    def test_metadata_receipts_change_with_the_current_source_universe(self):
        _, _, single = self.forensics(self.single)
        _, _, duo = self.forensics(self.duo)
        self.assertNotEqual(single.source_snapshot_digest,
                            duo.source_snapshot_digest)
        self.assertNotEqual(single.provenance.posture_digest,
                            duo.provenance.posture_digest)
        self.assertNotEqual(single.report_digest, duo.report_digest)


if __name__ == "__main__":
    unittest.main()
