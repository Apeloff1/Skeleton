"""Adversarial source-policy transition, provenance and retrieval comparator tests.

Runs against the existing complete Dragon Atlas canonical CrawlRun fixtures.
Every output is offline, source-only, read-only and review-held. No network,
Mongo, external provider, device, credentials or publication authority.
"""
from __future__ import annotations

from dataclasses import replace
import unittest

import test_ai_webcrawler_dragon_atlas as fixtures

from skeleton.ai.webcrawler.dragon_campaign_stack import (
    CampaignMandate, SourcePolicyDecision, ResearchClaim, ClaimCitation,
    IndependenceAttestation, SourceLink, project_source_policy,
    assess_policy_invalidation, PassageJudgment, evaluate_fused_retrieval,
    compare_retrieval_benchmarks, inspect_crawl_campaign,
    assess_claim_matrix, verify_current_citations, compose_dragon_atlas,
)


class CrawlerPolicyAndBenchmarkTest(unittest.TestCase):
    def setUp(self) -> None:
        f = fixtures.DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid"
        )
        f.setUp()
        self.f = f
        self.snapshot = f.with_sources(
            ("https://example.com/archive", fixtures.research_text()),
        )
        self.atlas = f.atlas(self.snapshot)
        self.source_id = next(iter(self.snapshot["sources"]))
        self.now = f.now + 3

    def policy(self, decisions):
        return project_source_policy(
            self.f.mandate, self.snapshot, decisions,
            now=self.now, authorized=True,
            policy_snapshot_authenticated=True,
        )

    def pair(self, *, status="withdrawn", revision=2):
        initial = self.f.policies(self.snapshot)
        return (
            self.policy(initial),
            self.policy((replace(
                initial[0], status=status, policy_revision=revision,
            ),)),
        )

    def judge(self, grade=3, operator_reviewed=True):
        hit = self.atlas.retrieval.results[0]
        return PassageJudgment(
            objective_id="archive-method",
            source_id=hit.source_id, passage_hash=hit.passage_hash,
            start=hit.start, end=hit.end, grade=grade,
            operator_reference="operator-labeled-benchmark",
            operator_reviewed=operator_reviewed,
        )

    def benchmark(self, labels, *, top_k=10):
        return evaluate_fused_retrieval(
            self.f.mandate, self.atlas.workbench.objectives,
            self.atlas.lattice, self.atlas.index, self.atlas.retrieval,
            labels, now=self.now, authorized=True, top_k=top_k,
        )

    def test_withdrawal_invalidates_index_and_context(self):
        old, current = self.pair()
        impact = assess_policy_invalidation(
            self.f.mandate, old, current, now=self.now,
            authorized=True, retrieval=self.atlas.retrieval,
            context=self.atlas.context,
        )
        self.assertEqual(impact.transitions[0].disposition,
                         "source_use_withdrawn")
        self.assertIn(self.source_id, impact.affected_index_source_ids)
        self.assertIn(self.source_id, impact.affected_context_source_ids)
        self.assertTrue(impact.requires_index_rebuild)
        self.assertTrue(impact.requires_context_rebuild)
        self.assertFalse(impact.automatic_publication_authority)
        self.assertFalse(impact.authenticated_latest_policy)

    def test_same_status_new_revision_requires_revalidation(self):
        old, current = self.pair(status="review_scoped")
        impact = assess_policy_invalidation(
            self.f.mandate, old, current, now=self.now, authorized=True,
        )
        self.assertEqual(impact.transitions[0].disposition,
                         "policy_revision_changed")
        self.assertTrue(impact.requires_context_rebuild)
        self.assertEqual(impact.lineage.affected_source_ids, (self.source_id,))

    def test_same_policy_has_no_invalidation(self):
        first = self.policy(self.f.policies(self.snapshot))
        result = assess_policy_invalidation(
            self.f.mandate, first, first, now=self.now, authorized=True,
        )
        self.assertFalse(result.requires_context_rebuild)
        self.assertFalse(result.requires_index_rebuild)
        self.assertEqual(result.transitions, ())
        self.assertEqual(result.evidence, ())

    def test_policy_reenable_does_not_auto_restore_old_context(self):
        earlier = self.policy((replace(
            self.f.policies(self.snapshot)[0],
            status="withdrawn", policy_revision=2,
        ),))
        restored = self.policy((replace(
            self.f.policies(self.snapshot)[0],
            status="review_scoped", policy_revision=3,
        ),))
        impact = assess_policy_invalidation(
            self.f.mandate, earlier, restored,
            now=self.now, authorized=True,
        )
        self.assertTrue(impact.requires_context_rebuild)
        self.assertTrue(impact.requires_claim_review)
        self.assertEqual(impact.transitions[0].disposition,
                         "source_use_reenabled_requires_fresh_review")
        self.assertFalse(impact.automatic_publication_authority)

    def test_policy_rollback_is_rejected(self):
        first, next_policy = self.pair(status="withdrawn", revision=2)
        with self.assertRaises(ValueError):
            assess_policy_invalidation(
                self.f.mandate, next_policy, first,
                now=self.now, authorized=True,
            )

    def test_policy_reenable_with_later_revision_stays_review_held(self):
        earlier = self.policy((replace(
            self.f.policies(self.snapshot)[0],
            status="withdrawn", policy_revision=1,
        ),))
        newest = self.policy((replace(
            self.f.policies(self.snapshot)[0],
            status="review_scoped", policy_revision=2,
        ),))
        impact = assess_policy_invalidation(
            self.f.mandate, earlier, newest,
            now=self.now, authorized=True,
        )
        self.assertEqual(impact.transitions[0].disposition,
                         "source_use_reenabled_requires_fresh_review")
        self.assertTrue(impact.requires_claim_review)

    def test_policy_rejects_source_universe_change(self):
        other_snapshot = self.f.with_sources(
            ("https://example.org/research", fixtures.research_text("b")),
        )
        new = project_source_policy(
            self.f.mandate, other_snapshot,
            self.f.policies(other_snapshot),
            now=self.now, authorized=True,
            policy_snapshot_authenticated=True,
        )
        old = self.policy(self.f.policies(self.snapshot))
        with self.assertRaises(PermissionError):
            assess_policy_invalidation(
                self.f.mandate, old, new,
                now=self.now, authorized=True,
            )

    def test_policy_rejects_foreign_mandate(self):
        old, current = self.pair()
        foreign = replace(
            self.f.mandate,
            scope=replace(self.f.scope, tenant_id="foreign-tenant"),
        )
        with self.assertRaises(PermissionError):
            assess_policy_invalidation(
                foreign, old, current,
                now=self.now, authorized=True,
            )

    def test_policy_unsupported_source_lineage_rejected(self):
        old, current = self.pair()
        with self.assertRaises(ValueError):
            assess_policy_invalidation(
                self.f.mandate, old, current,
                now=self.now, authorized=True,
                links=(SourceLink("a"*64, self.source_id, "derived_from"),),
            )

    def test_policy_propagates_to_derived_sources(self):
        snapshot = self.f.with_sources(
            ("https://example.com/archive", fixtures.research_text("a")),
            ("https://example.org/research", fixtures.research_text("b")),
        )
        ids = sorted(snapshot["sources"])
        first = self.f.policies(snapshot)
        old = project_source_policy(
            self.f.mandate, snapshot, first,
            now=self.now, authorized=True,
            policy_snapshot_authenticated=True,
        )
        current = project_source_policy(
            self.f.mandate, snapshot,
            tuple(replace(row, status="withdrawn", policy_revision=2)
                  if row.source_id == ids[0] else row for row in first),
            now=self.now, authorized=True,
            policy_snapshot_authenticated=True,
        )
        impact = assess_policy_invalidation(
            self.f.mandate, old, current,
            links=(SourceLink(ids[1], ids[0], "derived_from"),),
            now=self.now, authorized=True,
        )
        self.assertEqual(impact.lineage.affected_source_ids, tuple(ids))
        self.assertEqual(impact.evidence[1].withdrawal_kind,
                         "derivative_source_lineage")

    def test_policy_propagates_to_claim_ids(self):
        inspection = inspect_crawl_campaign(
            self.snapshot, self.f.mandate,
            now=self.now, authorized=True,
        )
        passage = inspection.evidence.passages[0]
        citation = ClaimCitation(
            "claim-archive", passage.source_id, passage.passage_hash,
            "supports", 0.9, "operator evidence review only",
        )
        claim = ResearchClaim(
            "claim-archive", "This source contains archive methods",
            "archive-method",
        )
        checks = verify_current_citations(
            self.f.mandate, self.snapshot, inspection.evidence.passages,
            now=self.now, authorized=True,
        )
        matrix = assess_claim_matrix(
            self.f.mandate, (claim,), (citation,),
            inspection.evidence.passages, checks,
            now=self.now, authorized=True,
        )
        old, new = self.pair()
        impact = assess_policy_invalidation(
            self.f.mandate, old, new, matrix=matrix,
            now=self.now, authorized=True,
        )
        self.assertEqual(impact.affected_claim_ids, ("claim-archive",))
        self.assertEqual(impact.affected_objective_ids, ("archive-method",))

    def test_context_must_be_bound_to_retrieval_for_invalidation(self):
        old, new = self.pair()
        with self.assertRaises(ValueError):
            assess_policy_invalidation(
                self.f.mandate, old, new, context=self.atlas.context,
                now=self.now, authorized=True,
            )

    def test_unlabeled_benchmark_has_no_fabricated_score(self):
        result = self.benchmark(())
        self.assertIsNone(result.macro_ndcg_at_k)
        self.assertIsNone(result.macro_recall_at_k)
        self.assertEqual(result.unlabeled_objective_count, 1)
        self.assertFalse(result.performance_certified)

    def test_reviewed_relevance_receipt_has_valid_metrics(self):
        result = self.benchmark((self.judge(),))
        self.assertEqual(result.objectives[0].relevant_judgments, 1)
        self.assertEqual(result.objectives[0].relevant_found, 1)
        self.assertEqual(result.objectives[0].recall_at_k, 1.0)
        self.assertIsNotNone(result.macro_ndcg_at_k)
        self.assertGreater(result.macro_ndcg_at_k, 0)
        self.assertFalse(result.external_fact_verification)

    def test_relevance_rank_comparator_same_corpus_delta_zero(self):
        label = self.judge()
        a, b = self.benchmark((label,)), self.benchmark((label,))
        compared = compare_retrieval_benchmarks(a, b)
        self.assertTrue(compared.compatible)
        self.assertEqual(compared.macro_ndcg_delta, 0.0)
        self.assertFalse(compared.superiority_certified)
        self.assertIn("no_observed_ndcg_improvement", compared.review_reasons)

    def test_wrong_source_judgment_rejected(self):
        with self.assertRaises(PermissionError):
            self.benchmark((
                replace(self.judge(), source_id="e"*64),
            ))

    def test_changed_anchor_judgment_rejected(self):
        with self.assertRaises(PermissionError):
            self.benchmark((
                replace(self.judge(), start=self.judge().start+1),
            ))

    def test_unreviewed_judgment_rejected(self):
        with self.assertRaises(PermissionError):
            self.benchmark((self.judge(operator_reviewed=False),))

    def test_duplicate_judgment_rejected(self):
        label = self.judge()
        with self.assertRaises(ValueError):
            self.benchmark((label, label))

    def test_zero_positive_judgment_does_not_invent_recall(self):
        result = self.benchmark((self.judge(grade=0),))
        self.assertIsNone(result.objectives[0].recall_at_k)
        self.assertIsNone(result.objectives[0].normalized_dcg_at_k)
        self.assertIn("no_positive_relevance_labels",
                      result.objectives[0].limitations)

    def test_benchmark_rejects_out_of_bounds_k(self):
        with self.assertRaises(ValueError):
            self.benchmark((self.judge(),), top_k=0)

    def test_benchmark_rejects_forged_label_universe_comparison(self):
        good = self.benchmark((self.judge(grade=3),))
        alternative = self.benchmark((self.judge(grade=2),))
        with self.assertRaises(PermissionError):
            compare_retrieval_benchmarks(good, alternative)

    def test_retrieval_ranking_is_not_factual_verification(self):
        benchmark = self.benchmark((self.judge(),))
        self.assertFalse(benchmark.performance_certified)
        self.assertFalse(benchmark.autonomous_optimization_authorized)
        self.assertFalse(benchmark.external_fact_verification)

    def test_transitive_derivation_through_unattested_source(self):
        snapshot = self.f.with_sources(
            ("https://example.com/archive", fixtures.research_text("a")),
            ("https://example.org/research", fixtures.research_text("b")),
            ("https://example.com/origin", fixtures.research_text("c")),
        )
        ids = sorted(snapshot["sources"])
        inspection = inspect_crawl_campaign(
            snapshot, self.f.mandate,
            now=self.now, authorized=True,
        )
        passages = {}
        for passage in inspection.evidence.passages:
            passages.setdefault(passage.source_id, passage)
        self.assertEqual(len(passages), 3)
        claim = ResearchClaim(
            "claim-archive", "Archive research method citation",
            "archive-method",
        )
        references = tuple(ClaimCitation(
            claim.claim_id, ident, passages[ident].passage_hash,
            "supports", 0.9, "human provenance assessment pending",
        ) for ident in (ids[0], ids[2]))
        groups = (
            IndependenceAttestation(
                "group-one", (ids[0],), "review-reference-one", True,
            ),
            IndependenceAttestation(
                "group-two", (ids[2],), "review-reference-two", True,
            ),
        )
        atlas = compose_dragon_atlas(
            self.f.mandate, snapshot, objectives=(self.f.objective(),),
            source_policies=self.f.policies(snapshot),
            policy_snapshot_authenticated=True,
            now=self.now, authorized=True,
            claims=(claim,), claim_citations=references,
            independence_attestations=groups,
            source_links=(
                SourceLink(ids[1], ids[0], "derived_from"),
                SourceLink(ids[2], ids[1], "revision_of"),
            ),
        )
        self.assertEqual(atlas.independence.ambiguous_group_count, 2)
        self.assertEqual(
            atlas.independence.claims[0].effective_support_groups_upper_bound,
            0,
        )
        self.assertTrue(any(
            "shared_derivation_ancestry" in x.relationship
            for x in atlas.independence.findings
        ))


if __name__ == "__main__":
    unittest.main()
