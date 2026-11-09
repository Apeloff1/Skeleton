"""Fifth-wave Dragon source-quality, rank custody and risk-survivability tests.

No real URL is fetched, no source is published, and no worker or database is
mutated. The canonical CrawlRun fixtures exercise the real Atlas pipeline.
Isolated synthetic frame edits exercise scanners that upstream capture policy
would otherwise reject before the research stage.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import unittest

import test_ai_webcrawler_dragon_atlas as fixtures
from skeleton.ai.webcrawler.dragon_campaign_stack.forensics import (
    compose_atlas_forensics, verify_atlas_forensics, bind_selected_frames,
    inspect_extraction_quality, audit_query_support, audit_selected_origins,
    measure_selection_fairness, simulate_risk_ablations,
    inspect_script_coverage, plan_review_capacity,
)


class DragonWave5Tests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid",
        )
        self.f.setUp()
        self.now = self.f.now + 3
        self.body = fixtures.research_text("wavefive")
        self.one = self.f.with_sources(("https://example.com/a", self.body))
        self.two = self.f.with_sources(
            ("https://example.com/a", self.body),
            ("https://example.org/b", self.body),
        )

    def inspect(self, snapshot=None, **kwargs):
        actual = self.f.empty if snapshot is None else snapshot
        atlas = self.f.atlas(actual, **kwargs)
        report = compose_atlas_forensics(
            self.f.mandate, actual, atlas,
            now=self.now, authorized=True,
        )
        frames = bind_selected_frames(
            self.f.mandate, actual, atlas.policies, atlas.retrieval,
            now=self.now, authorized=True,
        )
        return actual, atlas, frames, report

    def test_empty_exact_26_stage_chain_is_review_only(self):
        snapshot, atlas, frames, report = self.inspect()
        self.assertEqual(len(report.stages), 26)
        self.assertEqual(report.selected_anchor_count, 0)
        self.assertEqual(report.query_support.selected_anchors_checked, 0)
        self.assertEqual(report.extraction.findings, ())
        self.assertEqual(report.origins.findings, ())
        self.assertFalse(report.risk_ablation.automatic_source_withdrawal)
        self.assertTrue(report.human_review_required)
        verify_atlas_forensics(
            self.f.mandate, snapshot, atlas, report,
            now=self.now, authorized=True,
        )

    def test_exact_canonical_source_to_26_stage_replay(self):
        snapshot, atlas, frames, report = self.inspect(self.one)
        self.assertGreater(report.selected_anchor_count, 0)
        self.assertEqual(report.extraction.frame_set_digest, frames.frame_set_digest)
        self.assertEqual(report.query_support.retrieval_digest, atlas.retrieval.fusion_digest)
        self.assertEqual(report.origins.source_snapshot_digest, snapshot["snapshot_digest"])
        self.assertEqual(report.selection_fairness.objective_plan_digest,
                         atlas.workbench.objectives.plan_digest)
        self.assertEqual(report.script_coverage.objective_plan_digest,
                         atlas.workbench.objectives.plan_digest)
        self.assertEqual(report.risk_ablation.objective_plan_digest,
                         atlas.workbench.objectives.plan_digest)
        self.assertEqual(report.stages[19].name, "captured_extraction_quality_diagnostics")
        self.assertEqual(report.stages[20].name, "operator_query_rank_support_audit")
        self.assertEqual(report.stages[21].name, "captured_origin_redirect_hygiene")
        self.assertEqual(report.stages[22].name, "objective_selection_fairness_metrics")
        self.assertEqual(report.stages[23].name, "conservative_risky_source_ablation")
        self.assertEqual(report.stages[24].name, "script_coverage_lexical_limitations")
        self.assertEqual(report.stages[25].name, "review_only_forensic_queue")
        verify_atlas_forensics(
            self.f.mandate, snapshot, atlas, report,
            now=self.now, authorized=True,
        )

    def test_dual_reconstruction_is_deterministic(self):
        _, _, _, a = self.inspect(self.two)
        _, _, _, b = self.inspect(self.two)
        self.assertEqual(a, b)
        self.assertEqual(a.report_digest, b.report_digest)

    def test_source_body_is_not_serialized_into_wave5_report(self):
        _, _, _, report = self.inspect(self.one)
        serial = json.dumps(asdict(report))
        self.assertNotIn(self.body, serial)
        self.assertFalse(report.extraction.external_text_exported)
        self.assertFalse(report.origins.source_url_paths_exported)
        self.assertFalse(report.script_coverage.external_text_translated)
        self.assertFalse(report.query_support.live_search_reexecuted)

    def test_extraction_quality_empty_has_no_artificial_findings(self):
        _, _, frames, report = self.inspect()
        a = inspect_extraction_quality(frames)
        self.assertEqual(a.findings, ())
        self.assertEqual(a.compared_bytes, 0)
        self.assertEqual(a.held_source_ids, ())
        self.assertFalse(a.extraction_fidelity_certified)

    def test_extraction_quality_detects_markup_and_repeated_characters(self):
        _, _, frames, _ = self.inspect(self.one)
        sample = "<div>text</div> <b>bad</b> <p>html</p> " + "X" * 60
        synthetic = replace(frames, frames=(
            replace(frames.frames[0], text=sample),
        ))
        a = inspect_extraction_quality(synthetic)
        flags = a.findings[0].review_codes
        self.assertIn("html_markup_residue", flags)
        self.assertIn("repeated_character_payload", flags)
        self.assertTrue(a.held_source_ids)
        self.assertFalse(a.findings[0].extraction_verified)

    def test_extraction_quality_enforces_per_passage_byte_limit(self):
        _, _, frames, _ = self.inspect(self.one)
        synthetic = replace(frames, frames=(
            replace(frames.frames[0], text="x" * 600),
        ))
        with self.assertRaises(ValueError):
            inspect_extraction_quality(synthetic, max_passage_bytes=128)

    def test_extraction_quality_rejects_invalid_ratio(self):
        _, _, frames, _ = self.inspect(self.one)
        with self.assertRaises(ValueError):
            inspect_extraction_quality(frames, sparse_word_ratio=-.1)

    def test_extraction_quality_flags_control_characters(self):
        _, _, frames, _ = self.inspect(self.one)
        modified = replace(frames, frames=(replace(
            frames.frames[0], text="archive\x01 capture method"
        ),))
        a = inspect_extraction_quality(modified)
        self.assertIn("nonprintable_extraction_characters",
                      a.findings[0].review_codes)

    def test_query_support_counts_current_selected_rank_provenance(self):
        _, atlas, frames, report = self.inspect(self.one)
        q = report.query_support
        self.assertEqual(q.selected_anchors_checked, len(atlas.retrieval.results))
        self.assertEqual(q.lattice_digest, atlas.lattice.lattice_digest)
        self.assertEqual(q.findings[0].objective_id, "archive-method")
        self.assertGreater(q.findings[0].selected_query_variants, 0)
        self.assertFalse(q.source_relevance_human_verified)

    def test_query_support_accepts_actual_bm25_ranker(self):
        _, atlas, frames, report = self.inspect(
            self.one, retrieval_mode="lexical_bm25",
        )
        self.assertGreater(report.query_support.selected_anchors_checked, 0)
        self.assertEqual(report.query_support.retrieval_digest,
                         atlas.retrieval.fusion_digest)

    def test_query_support_refuses_forged_rank_index(self):
        _, atlas, frames, _ = self.inspect(self.one)
        old = atlas.retrieval.results[0]
        synthetic = replace(atlas.retrieval, results=(
            replace(old, query_rank_support=((10000, 1),)),
        ) + atlas.retrieval.results[1:])
        with self.assertRaises(PermissionError):
            audit_query_support(frames, atlas.lattice, synthetic)

    def test_query_support_refuses_duplicate_query_index(self):
        _, atlas, frames, _ = self.inspect(self.one)
        original = atlas.retrieval.results[0]
        pair = original.query_rank_support[0]
        synthetic = replace(atlas.retrieval, results=(
            replace(original, query_rank_support=(pair, pair)),
        ) + atlas.retrieval.results[1:])
        with self.assertRaises(ValueError):
            audit_query_support(frames, atlas.lattice, synthetic)

    def test_query_support_refuses_forged_matching_query(self):
        _, atlas, frames, _ = self.inspect(self.one)
        original = atlas.retrieval.results[0]
        synthetic = replace(atlas.retrieval, results=(
            replace(original, matched_queries=("external injected query",)),
        ) + atlas.retrieval.results[1:])
        with self.assertRaises(PermissionError):
            audit_query_support(frames, atlas.lattice, synthetic)

    def test_query_support_refuses_cross_run_fusion(self):
        _, atlas, frames, _ = self.inspect(self.one)
        forged = replace(atlas.retrieval, source_snapshot_digest="e" * 64)
        with self.assertRaises(PermissionError):
            audit_query_support(frames, atlas.lattice, forged)

    def test_origin_report_does_not_reproduce_url_paths(self):
        snapshot, atlas, frames, report = self.inspect(self.one)
        origin = report.origins.findings[0]
        self.assertEqual(origin.host, "example.com")
        self.assertEqual(origin.canonical_query_parameter_count, 0)
        self.assertFalse(origin.raw_url_exported)
        self.assertFalse(report.origins.destination_network_verified)
        self.assertNotIn("https://example.com/a", json.dumps(asdict(report.origins)))

    def test_url_query_secret_name_gets_review_not_value_export(self):
        marker = "VERBATIM_TEST_VALUE_NEVER_EXPORT_0001"
        captured = self.f.with_sources((
            "https://example.com/a?token=" + marker, self.body,
        ))
        _, _, frames, report = self.inspect(captured)
        self.assertTrue(report.origins.risky_query_parameter_sources)
        self.assertTrue(any(row.sensitive_parameter_name_count for row
                            in report.origins.findings))
        self.assertNotIn(marker, json.dumps(asdict(report.origins)))
        self.assertFalse(report.origins.source_url_paths_exported)
        self.assertTrue(any(task.reason ==
                            "source_origin:possible_sensitive_query_parameter_name"
                            for task in report.reviews.tasks))

    def test_origin_requires_current_unmutated_snapshot(self):
        snapshot, atlas, frames, _ = self.inspect(self.one)
        altered = dict(snapshot)
        altered["snapshot_digest"] = "0" * 64
        with self.assertRaises(Exception):
            audit_selected_origins(
                self.f.mandate, altered, frames,
                now=self.now, authorized=True,
            )

    def test_origin_rejects_lapsed_consent(self):
        _, _, frames, _ = self.inspect(self.one)
        with self.assertRaises(PermissionError):
            audit_selected_origins(
                self.f.mandate, self.one, frames,
                now=self.f.now + 3601, authorized=True,
            )

    def test_selection_fairness_no_selected_source_has_zero_concentration(self):
        _, _, frames, report = self.inspect()
        row = report.selection_fairness.findings[0]
        self.assertEqual(row.selected_sources, 0)
        self.assertEqual(row.largest_source_character_share, 0)
        self.assertFalse(row.source_dominance_review)
        self.assertFalse(row.host_dominance_review)
        self.assertFalse(row.independent_evidence_confirmed)

    def test_selection_fairness_flags_single_source_dominance(self):
        _, _, frames, report = self.inspect(self.one)
        row = report.selection_fairness.findings[0]
        self.assertEqual(row.selected_sources, 1)
        self.assertEqual(row.largest_source_character_share, 1)
        self.assertTrue(row.source_dominance_review)
        self.assertTrue(row.host_dominance_review)

    def test_selection_fairness_bounds_efficiency_metrics(self):
        _, _, frames, report = self.inspect(self.two)
        for row in report.selection_fairness.findings:
            self.assertLessEqual(row.largest_source_character_share, 1)
            self.assertLessEqual(row.largest_host_character_share, 1)
            self.assertGreaterEqual(row.effective_sources_by_characters, 0)
            self.assertLessEqual(row.normalized_source_entropy, 1.000001)
        self.assertFalse(report.selection_fairness.factual_relevance_confirmed)

    def test_selection_fairness_rejects_foreign_mandate(self):
        _, atlas, frames, _ = self.inspect(self.one)
        forged = replace(frames, mandate_digest="d" * 64)
        with self.assertRaises(PermissionError):
            measure_selection_fairness(forged, atlas.workbench.objectives)

    def test_risk_ablation_no_findings_never_revokes_any_source(self):
        _, _, frames, report = self.inspect(self.one)
        result = report.risk_ablation
        self.assertEqual(result.frame_set_digest, frames.frame_set_digest)
        self.assertFalse(result.automatic_source_withdrawal)
        self.assertFalse(result.additional_crawling_authorized)
        self.assertFalse(result.report_is_verified_fact)

    def test_risk_ablation_simulates_source_loss_without_mutation(self):
        _, atlas, frames, report = self.inspect(self.one)
        source = frames.frames[0].anchor.source_id
        security = replace(report.security, held_sources=(source,))
        result = simulate_risk_ablations(
            frames, atlas.workbench.objectives, security, report.privacy,
            report.active_content, report.extraction, report.origins,
        )
        self.assertIn(source, result.held_source_ids)
        self.assertEqual(result.findings[0].sources_after, 0)
        self.assertTrue(result.findings[0].no_usable_selected_evidence_in_scenario)
        self.assertFalse(result.automatic_source_withdrawal)

    def test_risk_ablation_rejects_cross_snapshot_source_labels(self):
        _, atlas, frames, report = self.inspect(self.one)
        security = replace(report.security, held_sources=("d" * 64,))
        with self.assertRaises(PermissionError):
            simulate_risk_ablations(
                frames, atlas.workbench.objectives, security, report.privacy,
                report.active_content, report.extraction, report.origins,
            )

    def test_script_coverage_empty_is_not_a_language_claim(self):
        _, _, frames, report = self.inspect()
        item = report.script_coverage.findings[0]
        self.assertEqual(item.scripts_observed, ())
        self.assertFalse(item.language_identified)
        self.assertFalse(report.script_coverage.new_query_executed)
        self.assertFalse(report.script_coverage.language_certainty_assessed)

    def test_script_coverage_cyrillic_text_triggers_lexical_review(self):
        _, atlas, frames, _ = self.inspect(self.one)
        sample = "Archive capture " + "Пример текста " * 5
        synthetic = replace(frames, frames=(
            replace(frames.frames[0], text=sample),
        ))
        report = inspect_script_coverage(
            synthetic, atlas.workbench.objectives,
        )
        row = report.findings[0]
        self.assertTrue(row.non_latin_selected_evidence)
        self.assertIn("cyrillic", row.scripts_observed)
        self.assertTrue(row.lexical_coverage_review)
        self.assertFalse(row.language_identified)

    def test_script_coverage_rejects_foreign_objective(self):
        _, atlas, frames, _ = self.inspect(self.one)
        original = frames.frames[0]
        synthetic = replace(frames, frames=(
            replace(original, anchor=replace(
                original.anchor, objective_ids=("attacker-provided-goal",),
            )),
        ))
        with self.assertRaises(PermissionError):
            inspect_script_coverage(synthetic, atlas.workbench.objectives)

    def test_script_coverage_rejects_unbounded_threshold(self):
        _, atlas, frames, _ = self.inspect(self.one)
        with self.assertRaises(ValueError):
            inspect_script_coverage(
                frames, atlas.workbench.objectives,
                min_non_latin_letters=0,
            )

    def test_human_review_queue_contains_source_dominance(self):
        _, _, _, report = self.inspect(self.one)
        self.assertTrue(any(x.reason == "selection:source_character_dominance"
                            for x in report.reviews.tasks))
        self.assertFalse(report.reviews.automatic_publication_permitted)

    def test_review_capacity_is_not_an_automated_review_decision(self):
        _, _, _, report = self.inspect(self.one)
        plan = plan_review_capacity(report.reviews, lanes=4)
        self.assertFalse(plan.human_reviews_performed)
        self.assertFalse(plan.task_completion_asserted)
        self.assertFalse(plan.external_workers_started)

    def test_wave5_receipt_replay_rejects_tampered_extraction(self):
        snapshot, atlas, _, report = self.inspect(self.one)
        fake = replace(report, extraction=replace(
            report.extraction, suspect_passages=123,
        ))
        with self.assertRaises(PermissionError):
            verify_atlas_forensics(
                self.f.mandate, snapshot, atlas, fake,
                now=self.now, authorized=True,
            )

    def test_wave5_receipt_replay_rejects_tampered_query_support(self):
        snapshot, atlas, _, report = self.inspect(self.one)
        fake = replace(report, query_support=replace(
            report.query_support, selected_anchors_checked=123,
        ))
        with self.assertRaises(PermissionError):
            verify_atlas_forensics(
                self.f.mandate, snapshot, atlas, fake,
                now=self.now, authorized=True,
            )

    def test_wave5_receipt_replay_rejects_forged_origin(self):
        snapshot, atlas, _, report = self.inspect(self.one)
        fake = replace(report, origins=replace(
            report.origins, risky_query_parameter_sources=("e" * 64,),
        ))
        with self.assertRaises(PermissionError):
            verify_atlas_forensics(
                self.f.mandate, snapshot, atlas, fake,
                now=self.now, authorized=True,
            )

    def test_wave5_chain_rejects_omitted_middle_stage(self):
        snapshot, atlas, _, report = self.inspect(self.one)
        bad = replace(report, stages=(
            *report.stages[:21], *report.stages[22:],
        ))
        with self.assertRaises(PermissionError):
            verify_atlas_forensics(
                self.f.mandate, snapshot, atlas, bad,
                now=self.now, authorized=True,
            )

    def test_wave5_cross_campaign_source_text_not_trusted(self):
        _, _, _, report = self.inspect(self.one)
        self.assertFalse(report.web_or_model_invoked)
        self.assertFalse(report.publication_authorized)
        self.assertFalse(report.new_crawl_authorized)
        self.assertFalse(report.source_text_exported)
        self.assertFalse(report.persistent_state_written)


if __name__ == "__main__":
    unittest.main()
