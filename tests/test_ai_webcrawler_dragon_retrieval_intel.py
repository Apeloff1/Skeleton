"""Dragon lexical ranking and source quantitative/temporal intelligence tests.

The suite uses actual canonical CrawlRun snapshot fixtures. All content remains
untrusted external evidence; results cannot issue a provider call, expand the
source allowlist, publish, or prove a remote site still contains a dated fact.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import unittest

import test_ai_webcrawler_dragon_atlas as samples
from skeleton.ai.webcrawler.dragon_campaign_stack import (
    LexicalRankingWeights, rank_ephemeral_research, lexical_report_to_fusion,
    PassageJudgment, propose_reviewed_query_terms,
    inspect_numeric_discrepancies, detect_temporal_mentions,
    verify_dragon_atlas_trace, compose_dragon_atlas,
)


class DragonRetrievalIntelligenceTest(unittest.TestCase):
    def setUp(self):
        self.f = samples.DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid"
        )
        self.f.setUp()
        self.now = self.f.now + 3
        self.snapshot = self.f.with_sources(
            ("https://example.com/archive", samples.research_text("ranked"))
        )
        self.atlas = self.f.atlas(self.snapshot)

    def ranked(self, **kwargs):
        return rank_ephemeral_research(
            self.f.mandate, self.snapshot,
            self.atlas.policies, self.atlas.index, self.atlas.lattice,
            now=self.now, authorized=True, **kwargs,
        )

    def label(self, grade=3, reviewed=True):
        hit = self.atlas.retrieval.results[0]
        return PassageJudgment(
            "archive-method", hit.source_id, hit.passage_hash,
            hit.start, hit.end, grade,
            "operator-approved-relevance", reviewed,
        )

    def feedback(self, labels, **kwargs):
        return propose_reviewed_query_terms(
            self.f.mandate, self.atlas.policies,
            self.atlas.workbench.objectives,
            self.atlas.lattice, self.atlas.index, labels,
            now=self.now, authorized=True, **kwargs,
        )

    def comparison(self, rows):
        snapshot = self.f.with_sources(*rows)
        atlas = self.f.atlas(snapshot)
        return snapshot, atlas

    def test_lexical_bm25_compiles_current_index_and_scores(self):
        report = self.ranked()
        self.assertGreater(len(report.selected), 0)
        self.assertGreater(len(report.scored_receipts), 0)
        self.assertGreater(report.indexed_term_count, 0)
        self.assertGreater(report.document_count, 0)
        self.assertEqual(report.source_snapshot_digest, self.snapshot["snapshot_digest"])
        self.assertFalse(report.ai_embedding_used)
        self.assertFalse(report.knowledge_promoted)

    def test_lexical_ranking_is_reproducible(self):
        a, b = self.ranked(), self.ranked()
        self.assertEqual(a.ranking_digest, b.ranking_digest)
        self.assertEqual(a.scored_receipts, b.scored_receipts)
        self.assertEqual(a.selected, b.selected)

    def test_lexical_result_is_bounded_and_source_diversified(self):
        report = self.ranked(max_results=1, max_context_chars=1200)
        self.assertLessEqual(len(report.selected), 1)
        self.assertLessEqual(report.context_chars, 1200)
        self.assertEqual(len({(x.source_id, x.passage_hash, x.start)
                              for x in report.selected}), len(report.selected))
        self.assertTrue(all(not x.knowledge_verified for x in report.selected))

    def test_lexical_score_receipt_has_real_query_rank(self):
        report = self.ranked()
        self.assertTrue(all(rank > 0 for hit in report.selected
                            for _, rank in hit.query_rank_support))
        self.assertTrue(all(receipt.combined >= 0
                            for receipt in report.scored_receipts))
        self.assertTrue(all(0 <= receipt.query_coverage <= 1
                            for receipt in report.scored_receipts))

    def test_lexical_adapter_produces_valid_downstream_fusion(self):
        ranked = self.ranked()
        fused = lexical_report_to_fusion(ranked)
        self.assertEqual(fused.results, ranked.selected)
        self.assertEqual(fused.lattice_digest, self.atlas.lattice.lattice_digest)
        self.assertEqual(fused.index_digest, self.atlas.index.index_digest)
        self.assertFalse(fused.publication_authorized)

    def test_lexical_pipeline_mode_reuses_all_review_safety_gates(self):
        atlas = self.f.atlas(self.snapshot, retrieval_mode="lexical_bm25")
        self.assertEqual(atlas.retrieval_mode, "lexical_bm25")
        self.assertIsNotNone(atlas.lexical_ranking)
        self.assertEqual(atlas.retrieval.results, atlas.lexical_ranking.selected)
        self.assertEqual(atlas.context.retrieval_digest, atlas.retrieval.fusion_digest)
        self.assertEqual(atlas.citations.admitted, len(atlas.retrieval.results))
        self.assertFalse(atlas.dispatch_authorized)
        verify_dragon_atlas_trace(
            self.f.mandate, self.snapshot, atlas,
            now=self.now, authorized=True,
        )

    def test_lexical_mode_empty_snapshot_fails_no_false_retrieval(self):
        atlas = self.f.atlas(self.f.empty, retrieval_mode="lexical_bm25")
        self.assertEqual(atlas.retrieval.results, ())
        self.assertEqual(atlas.lexical_ranking.document_count, 0)
        self.assertEqual(atlas.numeric_signals.mentions, ())
        self.assertEqual(atlas.temporal_signals.mentions, ())

    def test_lexical_mode_rejects_unknown_algorithm(self):
        with self.assertRaises(ValueError):
            self.f.atlas(self.snapshot, retrieval_mode="provider_embeddings")

    def test_lexical_weights_reject_unnormalized_mix(self):
        with self.assertRaises(ValueError):
            LexicalRankingWeights(bm25_weight=.9, query_coverage_weight=.5)

    def test_lexical_weights_reject_nonfinite_parameters(self):
        with self.assertRaises(ValueError):
            LexicalRankingWeights(k1=float("nan"))

    def test_lexical_rejects_forged_index_receipt(self):
        with self.assertRaises(PermissionError):
            rank_ephemeral_research(
                self.f.mandate, self.snapshot, self.atlas.policies,
                replace(self.atlas.index, index_digest="f"*64),
                self.atlas.lattice, now=self.now, authorized=True,
            )

    def test_lexical_rejects_stale_policy_snapshot(self):
        with self.assertRaises(PermissionError):
            rank_ephemeral_research(
                self.f.mandate, self.snapshot,
                replace(self.atlas.policies, source_snapshot_digest="f"*64),
                self.atlas.index, self.atlas.lattice,
                now=self.now, authorized=True,
            )

    def test_lexical_rejects_absent_authorization(self):
        with self.assertRaises(PermissionError):
            rank_ephemeral_research(
                self.f.mandate, self.snapshot, self.atlas.policies,
                self.atlas.index, self.atlas.lattice,
                now=self.now, authorized=False,
            )

    def test_lexical_rejects_scoring_receipt_capacity_overrun(self):
        with self.assertRaises(ValueError):
            self.ranked(max_receipts=1)

    def test_lexical_rejects_source_explicitly_withdrawn(self):
        withdrawn = self.f.policies(self.snapshot, status="withdrawn")
        atlas = compose_dragon_atlas(
            self.f.mandate, self.snapshot,
            objectives=(self.f.objective(),),
            source_policies=withdrawn,
            policy_snapshot_authenticated=True,
            retrieval_mode="lexical_bm25",
            now=self.now, authorized=True,
        )
        self.assertEqual(atlas.retrieval.results, ())
        self.assertEqual(atlas.lexical_ranking.selected, ())

    def test_feedback_requires_reviewed_human_relevance(self):
        with self.assertRaises(PermissionError):
            self.feedback((self.label(reviewed=False),))

    def test_feedback_proposes_untrusted_terms_without_activation(self):
        report = self.feedback((self.label(),))
        self.assertEqual(report.label_count, 1)
        self.assertFalse(report.automatic_query_approval)
        self.assertFalse(report.crawler_rights_extended)
        self.assertTrue(report.objectives[0].candidates)
        self.assertTrue(all(not x.is_authoritative_query
                            for x in report.objectives[0].candidates))
        self.assertTrue(all(x.proposed_weight > 0
                            for x in report.objectives[0].candidates))

    def test_feedback_does_not_convert_negative_labels_to_positive(self):
        report = self.feedback((self.label(grade=0),))
        self.assertEqual(report.objectives[0].reviewed_positive_labels, 0)
        self.assertEqual(report.objectives[0].candidates, ())

    def test_feedback_rejects_duplicate_label_source(self):
        label = self.label()
        with self.assertRaises(ValueError):
            self.feedback((label, label))

    def test_feedback_rejects_wrong_passage_hash(self):
        with self.assertRaises(PermissionError):
            self.feedback((replace(self.label(), passage_hash="c"*64),))

    def test_feedback_rejects_incompatible_policy(self):
        with self.assertRaises(PermissionError):
            propose_reviewed_query_terms(
                self.f.mandate,
                replace(self.atlas.policies, source_snapshot_digest="c"*64),
                self.atlas.workbench.objectives,
                self.atlas.lattice, self.atlas.index,
                (self.label(),), now=self.now, authorized=True,
            )

    def test_feedback_rejects_overlarge_label_window(self):
        with self.assertRaises(ValueError):
            self.feedback((self.label(),), max_labels=0)

    def test_feedback_uses_explicit_source_id_not_host_independence(self):
        report = self.feedback((self.label(),))
        self.assertTrue(all(x.reviewed_source_count == 1
                            for x in report.objectives[0].candidates))
        self.assertFalse(report.source_publication_authorized)

    def test_lexical_mode_feedback_remains_optional(self):
        atlas = self.f.atlas(
            self.snapshot, reviewed_relevance_labels=(self.label(),),
        )
        self.assertIsNotNone(atlas.feedback)
        self.assertEqual(atlas.feedback.label_count, 1)
        self.assertFalse(atlas.feedback.automatic_query_approval)
        verify_dragon_atlas_trace(
            self.f.mandate, self.snapshot, atlas,
            now=self.now, authorized=True,
        )

    def test_numeric_discrepancy_between_two_scoped_hosts(self):
        rows = (
            ("https://example.com/archive",
             "Archive capture methodology recorded a weight of 100 kg. " +
             samples.research_text("first")),
            ("https://example.org/research",
             "Archive capture methodology recorded a weight of 120 kg. " +
             samples.research_text("second")),
        )
        snapshot, atlas = self.comparison(rows)
        finding = atlas.numeric_signals
        self.assertTrue(finding.candidates)
        candidate = finding.candidates[0]
        self.assertEqual(candidate.normalized_unit, "mass_kg")
        self.assertGreater(candidate.relative_gap, 0.1)
        self.assertFalse(candidate.factual_contradiction_established)
        self.assertTrue(candidate.human_review_required)

    def test_numeric_kilogram_to_gram_normalization(self):
        rows = (
            ("https://example.com/archive",
             "Archive capture methodology reports 1 kg of archived material. " +
             samples.research_text("first")),
            ("https://example.org/research",
             "Archive capture methodology reports 1000 g of archived material. " +
             samples.research_text("second")),
        )
        _, atlas = self.comparison(rows)
        mentions = atlas.numeric_signals.mentions
        self.assertTrue(any(x.normalized_unit == "mass_kg"
                            and x.normalized_value == "1" for x in mentions))
        self.assertFalse(any(x.normalized_unit == "mass_kg"
                             for x in atlas.numeric_signals.candidates))

    def test_numeric_currency_pairs_do_not_infer_exchange_rates(self):
        rows = (
            ("https://example.com/archive",
             "Archive capture methodology cost $100 in the recorded experiment. " +
             samples.research_text("first")),
            ("https://example.org/research",
             "Archive capture methodology cost 90 EUR in the recorded experiment. " +
             samples.research_text("second")),
        )
        _, atlas = self.comparison(rows)
        currencies = {x.normalized_unit for x in atlas.numeric_signals.mentions}
        self.assertTrue({"USD", "EUR"}.issubset(currencies))
        self.assertFalse(any(x.normalized_unit in ("USD","EUR")
                             for x in atlas.numeric_signals.candidates))

    def test_numeric_signal_spans_remain_exact_retained_text(self):
        rows = (("https://example.com/archive",
                 "Archive capture methodology cost 120 kg of material. " +
                 samples.research_text("span")),)
        snapshot, atlas = self.comparison(rows)
        self.assertTrue(atlas.numeric_signals.mentions)
        for item in atlas.numeric_signals.mentions:
            retained = snapshot["sources"][item.source_id]["text"]
            self.assertEqual(retained[item.start:item.end], item.raw)

    def test_numeric_signal_rejects_stale_source_policy(self):
        with self.assertRaises(PermissionError):
            inspect_numeric_discrepancies(
                self.f.mandate, self.snapshot,
                replace(self.atlas.policies, policy_digest="f"*64,
                        source_snapshot_digest="f"*64),
                self.atlas.retrieval,
                now=self.now, authorized=True,
            )

    def test_numeric_signal_has_no_automatic_publication(self):
        self.assertFalse(self.atlas.numeric_signals.publication_authorized)
        self.assertEqual(self.atlas.numeric_signals.verified_claims_count, 0)

    def test_temporal_detects_explicit_iso_date_without_remote_refresh(self):
        rows = (
            ("https://example.com/archive",
             "Archive capture methodology was updated on 2026-11-05. " +
             samples.research_text("time")),
        )
        snap, atlas = self.comparison(rows)
        dates = atlas.temporal_signals.mentions
        self.assertTrue(any(x.iso_date == "2026-11-05" for x in dates))
        self.assertFalse(atlas.temporal_signals.actual_remote_update_checked)
        for finding in dates:
            self.assertEqual(
                snap["sources"][finding.source_id]["text"][finding.start:finding.end],
                finding.retained_text,
            )

    def test_temporal_rejects_invalid_calendar_date(self):
        rows = (
            ("https://example.com/archive",
             "Archive capture methodology was updated on 2026-02-30. " +
             samples.research_text("time")),
        )
        _, atlas = self.comparison(rows)
        self.assertGreater(atlas.temporal_signals.rejected_invalid_dates, 0)
        self.assertNotIn("2026-02-30",
                         {x.iso_date for x in atlas.temporal_signals.mentions})

    def test_temporal_accepts_leap_day(self):
        rows = (
            ("https://example.com/archive",
             "Archive capture methodology recorded 2024-02-29. " +
             samples.research_text("time")),
        )
        _, atlas = self.comparison(rows)
        self.assertIn("2024-02-29",
                      {x.iso_date for x in atlas.temporal_signals.mentions})

    def test_temporal_review_not_fact_verification(self):
        self.assertFalse(self.atlas.temporal_signals.event_ontology_verified)
        self.assertFalse(self.atlas.temporal_signals.actual_remote_update_checked)

    def test_temporal_withdrawal_suppresses_source_date_mentions(self):
        rows = (
            ("https://example.com/archive",
             "Archive capture methodology noted 2026-11-05. " +
             samples.research_text("time")),
        )
        snap = self.f.with_sources(*rows)
        atlas = compose_dragon_atlas(
            self.f.mandate, snap, objectives=(self.f.objective(),),
            source_policies=self.f.policies(snap, status="withdrawn"),
            policy_snapshot_authenticated=True,
            now=self.now, authorized=True,
        )
        self.assertEqual(atlas.temporal_signals.mentions, ())

    def test_full_pipeline_is_receipt_bound_and_repeatable(self):
        a = self.f.atlas(self.snapshot, retrieval_mode="lexical_bm25")
        b = self.f.atlas(self.snapshot, retrieval_mode="lexical_bm25")
        self.assertEqual(a.atlas_digest, b.atlas_digest)
        self.assertEqual(a.numeric_signals.report_digest, b.numeric_signals.report_digest)
        self.assertEqual(a.temporal_signals.signal_digest, b.temporal_signals.signal_digest)
        self.assertEqual(len(a.stages), 26)
        self.assertTrue(all(not x.content_may_be_trusted for x in a.stages))


if __name__ == "__main__":
    unittest.main()
