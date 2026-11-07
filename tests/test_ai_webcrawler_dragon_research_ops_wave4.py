"""Fourth-wave Dragon Atlas source usage, deficit, context and review tests."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import unittest

import test_ai_webcrawler_dragon_atlas as fixtures
from skeleton.ai.webcrawler.dragon_campaign_stack.forensics import (
    compose_atlas_forensics, verify_atlas_forensics, bind_selected_frames,
    compile_source_usage_map, synthesize_research_gaps, audit_context_budget,
    plan_review_capacity,
)


class DragonResearchOpsWave4Tests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid",
        )
        self.f.setUp()
        self.now = self.f.now + 3
        text = fixtures.research_text("researchops")
        self.single = self.f.with_sources(("https://example.com/a", text))
        self.duo = self.f.with_sources(
            ("https://example.com/a", text),
            ("https://example.org/b", text),
        )

    def compose(self, snapshot):
        atlas = self.f.atlas(snapshot)
        report = compose_atlas_forensics(
            self.f.mandate, snapshot, atlas,
            now=self.now, authorized=True,
        )
        frames = bind_selected_frames(
            self.f.mandate, snapshot, atlas.policies, atlas.retrieval,
            now=self.now, authorized=True,
        )
        return atlas, frames, report

    def test_empty_source_map_is_complete_without_fabricated_citation(self):
        atlas, frames, report = self.compose(self.f.empty)
        usage = report.usage
        self.assertEqual(usage.selected_anchor_count, 0)
        self.assertEqual(usage.selected_source_count, 0)
        self.assertEqual(usage.unrepresented_objectives, ("archive-method",))
        self.assertFalse(usage.factual_evidence_certified)
        self.assertFalse(usage.source_text_exported)

    def test_exact_source_map_is_traceable_to_retained_crawl(self):
        atlas, frames, report = self.compose(self.single)
        usage = report.usage
        self.assertEqual(usage.frame_set_digest, frames.frame_set_digest)
        self.assertEqual(usage.objective_plan_digest,
                         atlas.workbench.objectives.plan_digest)
        self.assertEqual(usage.selected_anchor_count, len(frames.frames))
        self.assertEqual(usage.selected_source_count, len(usage.source_uses))
        for row in usage.source_uses:
            self.assertTrue(row.passage_anchor_digests)
            self.assertEqual(len(set(row.passage_anchor_digests)),
                             row.selected_passage_count)
            self.assertFalse(row.approved_knowledge)

    def test_source_map_rejects_foreign_objective_identity(self):
        atlas, frames, _ = self.compose(self.single)
        first = frames.frames[0]
        tampered = replace(first, anchor=replace(
            first.anchor, objective_ids=("not-authorized",),
        ))
        synthetic = replace(frames, frames=(tampered,) + frames.frames[1:])
        with self.assertRaises(PermissionError):
            compile_source_usage_map(synthetic, atlas.workbench.objectives)

    def test_source_map_rejects_same_source_with_mismatched_host(self):
        atlas, frames, _ = self.compose(self.single)
        first = frames.frames[0]
        inconsistent = replace(first, anchor=replace(
            first.anchor, host="example.org",
        ))
        synthetic = replace(frames, frames=frames.frames + (inconsistent,))
        with self.assertRaises(PermissionError):
            compile_source_usage_map(synthetic, atlas.workbench.objectives)

    def test_source_map_rejects_duplicate_anchor_identity(self):
        atlas, frames, _ = self.compose(self.single)
        synthetic = replace(frames, frames=frames.frames + (frames.frames[0],))
        with self.assertRaises(ValueError):
            compile_source_usage_map(synthetic, atlas.workbench.objectives)

    def test_source_use_count_is_bounded_by_selected_evidence(self):
        _, frames, report = self.compose(self.duo)
        usage = report.usage
        self.assertLessEqual(usage.selected_source_count, usage.selected_anchor_count)
        self.assertEqual(usage.selected_anchor_count, len(frames.frames))
        self.assertTrue(all(len(x.objective_ids) > 0 for x in usage.source_uses))

    def test_gap_matrix_explicitly_carries_review_deficits(self):
        atlas, frames, report = self.compose(self.single)
        self.assertEqual(report.gaps.plan_digest,
                         atlas.workbench.objectives.plan_digest)
        self.assertEqual(report.gaps.source_usage_digest, report.usage.map_digest)
        self.assertEqual(len(report.gaps.gaps), 1)
        self.assertFalse(report.gaps.mission_complete)
        self.assertFalse(report.gaps.reviewed_knowledge_created)
        self.assertFalse(report.gaps.speculative_url_discovery_performed)
        self.assertFalse(report.gaps.gaps[0].autonomous_discovery_authorized)

    def test_missing_source_is_urgent_human_gap_not_fetch_instruction(self):
        _, _, report = self.compose(self.f.empty)
        row = report.gaps.gaps[0]
        self.assertEqual(row.urgency_tier, "urgent_human_research")
        self.assertIn("no_selected_source", row.review_deficit_codes)
        self.assertEqual(report.gaps.urgent_objectives, ("archive-method",))
        self.assertFalse(row.evidence_ready_for_publication)

    def test_provenance_limitations_propagate_to_research_gaps(self):
        _, _, report = self.compose(self.single)
        row = report.gaps.gaps[0]
        self.assertIn("source_provenance_limitations", row.review_deficit_codes)
        self.assertTrue(any(task.reason == "research_gap:source_provenance_limitations"
                            for task in report.reviews.tasks))

    def test_cross_snapshot_gap_synthesis_rejected(self):
        atlas, frames, report = self.compose(self.single)
        other_atlas, _, other = self.compose(self.duo)
        with self.assertRaises(PermissionError):
            synthesize_research_gaps(
                frames, atlas.workbench.objectives, report.grounding,
                report.resilience, report.exposure, other.provenance, report.usage,
            )

    def test_no_source_context_budget_is_zero_and_not_concentrated(self):
        _, _, report = self.compose(self.f.empty)
        b = report.context_budget
        self.assertEqual(b.total_selected_passages, 0)
        self.assertEqual(b.total_selected_chars, 0)
        self.assertEqual(b.total_selected_utf8_bytes, 0)
        self.assertFalse(b.source_concentration_review)
        self.assertIsNone(b.hottest_source_id)

    def test_selected_context_budget_accounting_is_exact(self):
        _, frames, report = self.compose(self.single)
        b = report.context_budget
        self.assertEqual(b.total_selected_chars, sum(
            len(row.text) for row in frames.frames
        ))
        self.assertEqual(b.total_selected_utf8_bytes, sum(
            len(row.text.encode("utf-8")) for row in frames.frames
        ))
        self.assertEqual(sum(x.selected_characters for x in b.source_budgets),
                         b.total_selected_chars)
        self.assertFalse(b.model_invoked)
        self.assertFalse(b.untrusted_text_exported)

    def test_context_byte_threshold_creates_review_holds(self):
        _, frames, report = self.compose(self.single)
        limited = audit_context_budget(
            self.f.mandate, frames, max_total_context_bytes=128,
        )
        self.assertTrue(limited.over_explicit_context_byte_limit)
        self.assertFalse(limited.publication_authorized)
        with self.assertRaises(ValueError):
            audit_context_budget(
                self.f.mandate, frames, max_total_context_bytes=1,
            )

    def test_context_budget_rejects_foreign_mandate(self):
        _, frames, _ = self.compose(self.single)
        modified = replace(frames, mandate_digest="f" * 64)
        with self.assertRaises(PermissionError):
            audit_context_budget(self.f.mandate, modified)

    def test_review_queue_includes_new_source_quality_work(self):
        _, _, report = self.compose(self.single)
        self.assertTrue(report.reviews.human_review_required)
        self.assertFalse(report.reviews.automatic_publication_permitted)
        self.assertTrue(any(
            task.reason.startswith("research_gap:") for task in report.reviews.tasks
        ))

    def test_review_capacity_plan_has_bounded_realistic_lanes(self):
        _, _, report = self.compose(self.single)
        plan = plan_review_capacity(
            report.reviews, lanes=2, budget_minutes=480,
        )
        self.assertLessEqual(plan.allocated_minutes, 480)
        self.assertTrue(all(0 <= x.reviewer_lane < 2 for x in plan.assignments))
        self.assertFalse(plan.human_reviews_performed)
        self.assertFalse(plan.task_completion_asserted)
        self.assertFalse(plan.external_workers_started)
        self.assertEqual(
            set(plan.selected_task_ids) | set(plan.deferred_task_ids),
            {x.task_id for x in report.reviews.tasks},
        )

    def test_review_capacity_budget_shortfall_remains_explicit(self):
        _, _, report = self.compose(self.single)
        plan = plan_review_capacity(
            report.reviews, budget_minutes=1,
        )
        self.assertEqual(plan.allocated_minutes, 0)
        self.assertEqual(plan.selected_task_ids, ())
        self.assertEqual(len(plan.deferred_task_ids), len(report.reviews.tasks))

    def test_critical_task_is_not_silently_dropped_from_review_budget(self):
        _, _, report = self.compose(self.single)
        queue = report.reviews
        self.assertTrue(queue.tasks)
        critical_task = replace(queue.tasks[0], risk="critical")
        synthetic = replace(queue, tasks=(critical_task,) + queue.tasks[1:])
        plan = plan_review_capacity(synthetic, budget_minutes=1)
        self.assertIn(critical_task.task_id, plan.unaddressed_critical_tasks)

    def test_review_capacity_rejects_false_model_permission(self):
        _, _, report = self.compose(self.single)
        queue = report.reviews
        bad = replace(queue, tasks=(
            replace(queue.tasks[0], model_may_decide=True),
        ) + queue.tasks[1:])
        with self.assertRaises(PermissionError):
            plan_review_capacity(bad)

    def test_review_capacity_rejects_auto_publication_queue(self):
        _, _, report = self.compose(self.single)
        bad = replace(report.reviews, automatic_publication_permitted=True)
        with self.assertRaises(PermissionError):
            plan_review_capacity(bad)

    def test_review_capacity_rejects_overlarge_requested_lane_count(self):
        _, _, report = self.compose(self.single)
        with self.assertRaises(ValueError):
            plan_review_capacity(report.reviews, lanes=100)

    def test_full_20_stage_trace_replays_on_current_canonical_source(self):
        atlas, _, report = self.compose(self.single)
        self.assertEqual(len(report.stages), 26)
        self.assertEqual(report.stages[16].name, "reverse_source_objective_usage")
        self.assertEqual(report.stages[17].name,
                         "policy_bound_research_deficit_matrix")
        self.assertEqual(report.stages[18].name,
                         "untrusted_context_resource_budget")
        self.assertEqual(report.stages[19].name, "captured_extraction_quality_diagnostics")
        self.assertEqual(report.stages[24].name, "script_coverage_lexical_limitations")
        self.assertEqual(report.stages[-1].name, "review_only_forensic_queue")
        verify_atlas_forensics(
            self.f.mandate, self.single, atlas, report,
            now=self.now, authorized=True,
        )

    def test_twenty_stage_chain_is_deterministic(self):
        _, _, left = self.compose(self.single)
        _, _, right = self.compose(self.single)
        self.assertEqual(left.report_digest, right.report_digest)
        self.assertEqual(left.stages, right.stages)
        self.assertEqual(left.reviews, right.reviews)

    def test_replay_catches_forged_budget_and_gap_data(self):
        atlas, _, report = self.compose(self.single)
        forged_budget = replace(report, context_budget=replace(
            report.context_budget, over_explicit_context_byte_limit=True,
        ))
        with self.assertRaises(PermissionError):
            verify_atlas_forensics(
                self.f.mandate, self.single, atlas, forged_budget,
                now=self.now, authorized=True,
            )
        forged_gap = replace(report, gaps=replace(
            report.gaps, urgent_objectives=("unapproved",),
        ))
        with self.assertRaises(PermissionError):
            verify_atlas_forensics(
                self.f.mandate, self.single, atlas, forged_gap,
                now=self.now, authorized=True,
            )

    def test_report_never_exports_retained_page_body(self):
        atlas, _, report = self.compose(self.single)
        body = fixtures.research_text("researchops")
        result = json.dumps(asdict(report))
        self.assertNotIn(body, result)
        self.assertFalse(report.source_text_exported)
        self.assertFalse(report.publication_authorized)
        self.assertFalse(report.gaps.reviewed_knowledge_created)

    def test_no_network_or_permission_grant_in_review_capacity(self):
        _, _, report = self.compose(self.single)
        plan = plan_review_capacity(report.reviews)
        self.assertFalse(plan.external_workers_started)
        self.assertTrue(all(x.would_require_authenticated_human_action
                            for x in plan.assignments))
        self.assertTrue(all(not x.task_completed for x in plan.assignments))


if __name__ == "__main__":
    unittest.main()
