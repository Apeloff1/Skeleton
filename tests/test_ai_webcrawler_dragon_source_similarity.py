"""Adversarial, canonical-policy-scoped near-duplicate research tests."""
from __future__ import annotations

from dataclasses import replace
from math import inf, nan
import unittest

import test_ai_webcrawler_dragon_atlas as fixtures
from skeleton.ai.webcrawler.dragon_campaign_stack import (
    inspect_selected_source_similarity, verify_dragon_atlas_trace,
)
from skeleton.ai.webcrawler.dragon_campaign_stack.near_duplicate_audit import (
    _shingles,
)


class DragonSourceSimilarityTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid",
        )
        self.f.setUp()
        self.now = self.f.now + 3
        self.mandate = self.f.mandate
        self.base = fixtures.research_text("sourceA")
        self.other = fixtures.research_text("sourceB")
        self.single = self.f.with_sources(
            ("https://example.com/a", self.base),
        )
        self.duo = self.f.with_sources(
            ("https://example.com/a", self.base),
            ("https://example.org/b", self.other),
        )

    def atlas(self, snapshot=None, **kwargs):
        return self.f.atlas(self.duo if snapshot is None else snapshot, **kwargs)

    def analyze(self, snapshot, atlas, **kwargs):
        return inspect_selected_source_similarity(
            self.mandate, snapshot, atlas.policies, atlas.retrieval,
            now=self.now, authorized=True, **kwargs,
        )

    def test_empty_source_universe_never_fabricates_similar_pages(self):
        a = self.atlas(self.f.empty)
        r = a.similarity
        self.assertEqual(r.considered_source_ids, ())
        self.assertEqual(r.compared_source_ids, ())
        self.assertEqual(r.similar_pairs, ())
        self.assertEqual(r.components, ())
        self.assertEqual(r.eligible_pair_count, 0)
        self.assertFalse(r.external_lookup_performed)

    def test_one_selected_source_has_no_comparison_pair(self):
        a = self.atlas(self.single)
        r = a.similarity
        self.assertLessEqual(len(r.considered_source_ids), 1)
        self.assertEqual(r.eligible_pair_count, 0)
        self.assertEqual(r.similar_pairs, ())
        self.assertFalse(r.lineage_verified)

    def test_exact_mirrors_from_different_hosts_raise_review_candidate(self):
        mirror = self.f.with_sources(
            ("https://example.com/a", self.base),
            ("https://example.org/b", self.base),
        )
        a = self.atlas(mirror)
        r = a.similarity
        if len(r.compared_source_ids) == 2:
            self.assertEqual(r.eligible_pair_count, 1)
            self.assertEqual(r.scored_pair_count, 1)
            pair = r.similar_pairs[0]
            self.assertEqual(pair.relation, "exact_content")
            self.assertEqual(pair.jaccard, 1)
            self.assertTrue(pair.cross_host)
            self.assertTrue(pair.needs_human_lineage_review)
            self.assertFalse(pair.shared_origin_established)
            self.assertEqual(r.cross_host_candidate_count, 1)
            self.assertEqual(len(r.components), 1)
            self.assertFalse(r.components[0].every_pair_verified_similar)
        self.assertFalse(r.factual_independence_certified)

    def test_small_editorial_append_creates_near_duplicate_lead(self):
        near = self.f.with_sources(
            ("https://example.com/a", self.base),
            ("https://example.org/b",
             self.base + "\nEditorial notice: this revision clarifies the method's date."),
        )
        a = self.atlas(near)
        r = a.similarity
        if len(r.compared_source_ids) == 2:
            self.assertTrue(r.similar_pairs)
            self.assertEqual(r.similar_pairs[0].relation,
                             "near_duplicate_review")
            self.assertFalse(r.similar_pairs[0].shared_origin_established)

    def test_different_text_never_claims_exact_hash_identity(self):
        a = self.atlas()
        for pair in a.similarity.similar_pairs:
            if pair.left_content_hash != pair.right_content_hash:
                self.assertNotEqual(pair.relation, "exact_content")
            self.assertFalse(pair.shared_origin_established)

    def test_similarity_digest_is_deterministic_from_current_canonical_source(self):
        a = self.atlas()
        reconstructed = self.analyze(self.duo, a)
        self.assertEqual(reconstructed, a.similarity)
        self.assertEqual(reconstructed.audit_digest, a.similarity.audit_digest)

    def test_verified_atlas_trace_includes_25th_policy_bounded_stage(self):
        a = self.atlas()
        self.assertEqual(len(a.stages), 26)
        self.assertEqual(a.stages[-1].name,
                         "objective_evidence_family_collapse_stress")
        verify_dragon_atlas_trace(
            self.mandate, self.duo, a, now=self.now, authorized=True,
        )

    def test_changing_pair_count_after_receipt_rejected_even_with_same_digest(self):
        a = self.atlas()
        changed = replace(a.similarity, scored_pair_count=100000)
        with self.assertRaises(PermissionError):
            verify_dragon_atlas_trace(
                self.mandate, self.duo,
                replace(a, similarity=changed), now=self.now, authorized=True,
            )

    def test_changed_source_policy_snapshot_rejected(self):
        a = self.atlas()
        stale = replace(a.policies, source_snapshot_digest="a" * 64)
        with self.assertRaises(PermissionError):
            inspect_selected_source_similarity(
                self.mandate, self.duo, stale, a.retrieval,
                now=self.now, authorized=True,
            )

    def test_withdrawn_capture_yields_no_near_duplicate_pairs(self):
        protected = self.f.with_sources(
            ("https://example.com/a", self.base),
            ("https://example.org/b", self.base),
        )
        from skeleton.ai.webcrawler.dragon_campaign_stack import compose_dragon_atlas
        a = compose_dragon_atlas(
            self.mandate, protected,
            objectives=(self.f.objective(),),
            source_policies=self.f.policies(protected, status="withdrawn"),
            policy_snapshot_authenticated=True,
            now=self.now, authorized=True,
        )
        self.assertEqual(a.similarity.considered_source_ids, ())
        self.assertEqual(a.similarity.compared_source_ids, ())
        self.assertEqual(a.similarity.similar_pairs, ())

    def test_foreign_or_modified_span_cannot_enter_similarity(self):
        a = self.atlas(self.single)
        self.assertTrue(a.retrieval.results)
        hit = a.retrieval.results[0]
        for changed in (
            replace(hit, passage_hash="f" * 64),
            replace(hit, source_hash="f" * 64),
            replace(hit, text="an invented source body"),
            replace(hit, canonical_url="https://example.org/foreign"),
            replace(hit, start=-1),
            replace(hit, end=10**8),
            replace(hit, host="evil.invalid"),
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(PermissionError):
                    inspect_selected_source_similarity(
                        self.mandate, self.single,
                        a.policies,
                        replace(a.retrieval, results=(changed,)),
                        now=self.now, authorized=True,
                    )

    def test_oversize_body_is_visible_hold_not_assumed_dissimilar(self):
        a = self.atlas(self.single)
        result = self.analyze(
            self.single, a, max_chars_per_source=128,
        )
        self.assertGreaterEqual(result.skipped_oversize_sources, 1)
        self.assertEqual(result.similar_pairs, ())
        self.assertEqual(len(result.held_source_ids),
                         result.skipped_oversize_sources)

    def test_comparison_bounds_reject_pair_budget_starvation(self):
        a = self.atlas()
        if len(a.similarity.compared_source_ids) > 1:
            with self.assertRaises(ValueError):
                self.analyze(self.duo, a, max_pairs=0)
        else:
            with self.assertRaises(ValueError):
                self.analyze(self.duo, a, max_sources=0)

    def test_short_content_shingles_have_no_false_similarity(self):
        self.assertFalse(_shingles("tiny", max_words=20))
        self.assertEqual(len(_shingles(
            "one two three four five", max_words=20,
        )), 2)
        with self.assertRaises(ValueError):
            _shingles(" ".join(f"term{x}" for x in range(30)),
                      max_words=16)

    def test_unicode_normalization_respects_casefold_and_fullwidth(self):
        left = _shingles(
            "Archive source methodology uses four independent validation measures",
            max_words=100,
        )
        right = _shingles(
            "ＡＲＣＨＩＶＥ SOURCE METHODOLOGY USES FOUR INDEPENDENT VALIDATION MEASURES",
            max_words=100,
        )
        self.assertEqual(left, right)

    def test_nonfinite_thresholds_denied(self):
        a = self.atlas()
        for value in (-1, 0, nan, inf, True, 1.1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.analyze(self.duo, a, jaccard_threshold=value)

    def test_untrusted_output_never_contains_source_page_body(self):
        a = self.atlas()
        r = a.similarity
        self.assertFalse(r.source_body_exposed)
        self.assertFalse(r.training_or_publication_granted)
        self.assertFalse(r.factual_independence_certified)
        self.assertFalse(r.lineage_verified)
        self.assertTrue(all(not hasattr(p, "text") for p in r.similar_pairs))

    def test_retrieval_suppressed_source_cannot_influence_candidates(self):
        a = self.atlas(self.single)
        new_retrieval = replace(a.retrieval, results=())
        result = inspect_selected_source_similarity(
            self.mandate, self.single, a.policies, new_retrieval,
            now=self.now, authorized=True,
        )
        self.assertEqual(result.considered_source_ids, ())
        self.assertEqual(result.scored_pair_count, 0)

    def test_cross_policy_revocation_set_mismatch_denied(self):
        a = self.atlas()
        modified = replace(a.retrieval, excluded_sources=("f" * 64,))
        with self.assertRaises(PermissionError):
            inspect_selected_source_similarity(
                self.mandate, self.duo, a.policies, modified,
                now=self.now, authorized=True,
            )


if __name__ == "__main__":
    unittest.main()
