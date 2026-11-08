"""Source-bound research robustness under host loss and evidence reuse.

The tests consume the canonical CrawlRun snapshots and literal selected
passages. No actual website, Mongo, external AI or OS worker is touched.
"""
from __future__ import annotations

from dataclasses import replace
from math import inf, nan
import copy
import unittest

import test_ai_webcrawler_dragon_atlas as fixtures
from skeleton.ai.webcrawler.dragon_campaign_stack import (
    ResearchObjective, SourcePolicyProjection, RetrievalRobustnessAudit,
    analyze_retrieval_robustness, compose_dragon_atlas,
    verify_dragon_atlas_trace,
)
from skeleton.ai.webcrawler.dragon_campaign_stack.contracts import digest
from skeleton.ai.webcrawler.operations import CrawlRun


class RetrievalRobustnessRegression(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid",
        )
        self.f.setUp()
        self.now = self.f.now + 3
        self.mandate = self.f.mandate
        self.empty = self.f.empty
        self.source = self.f.with_sources(
            ("https://example.com/archive", fixtures.research_text("robust1")),
        )
        self.double = self.f.with_sources(
            ("https://example.com/archive", fixtures.research_text("robust1")),
            ("https://example.org/research", fixtures.research_text("robust2")),
        )

    def atlas(self, snapshot=None, **kwargs):
        return self.f.atlas(
            self.empty if snapshot is None else snapshot, **kwargs,
        )

    def audit(self, snapshot, atlas, **kwargs):
        return analyze_retrieval_robustness(
            self.mandate, snapshot, atlas.workbench.objectives,
            atlas.policies, atlas.retrieval,
            now=self.now, authorized=True, **kwargs,
        )

    def multi(self, snapshot=None):
        current = self.double if snapshot is None else snapshot
        another = ResearchObjective(
            "alternative-method",
            "What alternate archive capture methods have been documented?",
            "counterexample", "verification", .8, 1, 1, 3600,
            required_terms=("archive", "capture"),
        )
        return compose_dragon_atlas(
            self.mandate, current,
            objectives=(self.f.objective(), another),
            source_policies=self.f.policies(current),
            policy_snapshot_authenticated=True,
            now=self.now, authorized=True,
        )

    def test_empty_snapshots_do_not_invent_evidence_or_host_independence(self):
        a = self.atlas()
        report = a.robustness
        self.assertEqual(report.selected_passages, 0)
        self.assertEqual(report.selected_sources, 0)
        self.assertEqual(report.selected_hosts, 0)
        self.assertEqual(report.analyses[0].host_ablation_risk, "no_selected_evidence")
        self.assertEqual(report.leave_one_host_out, ())
        self.assertEqual(report.flagged_objectives, ("archive-method",))
        self.assertFalse(report.verified_independence)
        self.assertFalse(report.counterfactual_ranking_executed)

    def test_single_observed_host_is_fragile_even_with_many_passages(self):
        a = self.atlas(self.source)
        self.assertGreater(len(a.retrieval.results), 0)
        report = a.robustness
        self.assertEqual(report.selected_hosts, 1)
        exposure = report.analyses[0]
        self.assertEqual(exposure.host_ablation_risk, "single_host")
        self.assertEqual(exposure.dominant_host, "example.com")
        self.assertEqual(exposure.dominant_host_fraction, 1)
        self.assertEqual(exposure.smallest_remaining_passages_after_host_removal, 0)
        self.assertEqual(exposure.smallest_remaining_sources_after_host_removal, 0)
        self.assertFalse(exposure.independent_corroboration_confirmed)

    def test_host_ablation_only_removes_current_selected_passages(self):
        a = self.atlas(self.double)
        report = a.robustness
        self.assertGreaterEqual(report.selected_hosts, 1)
        for item in report.leave_one_host_out:
            self.assertFalse(item.reranking_executed)
            self.assertTrue(item.hypothetical_selection_only)
            self.assertEqual(
                item.removed_selected_passages + item.surviving_selected_passages,
                len(a.retrieval.results),
            )
        self.assertEqual(
            sum(x.removed_selected_passages for x in report.leave_one_host_out),
            len(a.retrieval.results),
        )

    def test_two_distinct_hosts_are_not_independence_attestations(self):
        a = self.atlas(self.double)
        report = a.robustness
        self.assertFalse(report.verified_independence)
        self.assertTrue(report.source_bodies_excluded)
        self.assertTrue(all(not x.independent_corroboration_confirmed
                            for x in report.analyses))
        self.assertTrue(any("independent_ownership" in x
                            for x in report.limitations))

    def test_selected_sources_are_exact_current_source_identifiers(self):
        a = self.atlas(self.double)
        expected = {x.source_id for x in a.retrieval.results}
        self.assertEqual(a.robustness.selected_sources, len(expected))
        expected_hosts = {x.host for x in a.retrieval.results}
        self.assertEqual(a.robustness.selected_hosts, len(expected_hosts))

    def test_multiple_objective_reuse_does_not_mint_new_sources(self):
        a = self.multi()
        report = a.robustness
        self.assertEqual(len(report.analyses), 2)
        self.assertEqual(len(report.objective_reuse), 1)
        overlap = report.objective_reuse[0]
        self.assertLessEqual(overlap.source_jaccard, 1)
        self.assertGreaterEqual(overlap.source_jaccard, 0)
        self.assertLessEqual(
            len(overlap.overlapping_source_ids), report.selected_sources,
        )
        self.assertFalse(overlap.evidentiary_independence_proven)

    def test_objective_without_selected_evidence_is_not_omitted(self):
        current = self.double
        another = ResearchObjective(
            "unmatched-topic", "Zebra-only observations from unknown protocol",
            "method", "verification", .8, 1, 1, 3600,
            required_terms=("zebraonly",),
        )
        a = compose_dragon_atlas(
            self.mandate, current,
            objectives=(self.f.objective(), another),
            source_policies=self.f.policies(current),
            policy_snapshot_authenticated=True,
            now=self.now, authorized=True,
        )
        exposures = {x.objective_id: x for x in a.robustness.analyses}
        self.assertIn("unmatched-topic", exposures)
        self.assertEqual(exposures["unmatched-topic"].selected_passages, 0)
        self.assertEqual(exposures["unmatched-topic"].host_ablation_risk, "no_selected_evidence")

    def test_repeated_source_in_two_objectives_is_not_two_independence_groups(self):
        a = self.multi(self.source)
        report = a.robustness
        if a.retrieval.results:
            self.assertEqual(report.selected_sources, 1)
        self.assertTrue(all(not x.evidentiary_independence_proven
                            for x in report.objective_reuse))

    def test_deterministic_digest_for_fixed_snapshot_and_accepted_evidence(self):
        a = self.atlas(self.double)
        second = self.audit(self.double, a)
        self.assertEqual(second, a.robustness)
        self.assertEqual(second.audit_digest, a.robustness.audit_digest)

    def test_replay_verification_covers_new_24th_stage(self):
        a = self.atlas(self.double)
        self.assertEqual(len(a.stages), 26)
        self.assertEqual(a.stages[-1].name,
                         "objective_evidence_family_collapse_stress")
        verify_dragon_atlas_trace(
            self.mandate, self.double, a, now=self.now, authorized=True,
        )

    def test_altered_robustness_payload_fails_even_with_unchanged_digest(self):
        a = self.atlas(self.source)
        tampered = replace(a.robustness, selected_hosts=1000)
        with self.assertRaises(PermissionError):
            verify_dragon_atlas_trace(
                self.mandate, self.source,
                replace(a, robustness=tampered), now=self.now, authorized=True,
            )

    def test_robustness_report_denies_other_policy_snapshot(self):
        a = self.atlas(self.source)
        changed = replace(a.policies, source_snapshot_digest="f" * 64)
        with self.assertRaises(PermissionError):
            analyze_retrieval_robustness(
                self.mandate, self.source,
                a.workbench.objectives, changed, a.retrieval,
                now=self.now, authorized=True,
            )

    def test_robustness_report_denies_other_retrieval_snapshot(self):
        a = self.atlas(self.source)
        changed = replace(a.retrieval, source_snapshot_digest="f" * 64)
        with self.assertRaises(PermissionError):
            analyze_retrieval_robustness(
                self.mandate, self.source,
                a.workbench.objectives, a.policies, changed,
                now=self.now, authorized=True,
            )

    def test_robustness_report_denies_missing_source_policy_coverage(self):
        a = self.atlas(self.double)
        changed = replace(a.policies, excluded_source_ids=())
        # Policy covers all current captures only if no excluded IDs.
        if not a.policies.excluded_source_ids:
            changed = replace(a.policies, allowed_source_ids=())
        with self.assertRaises(PermissionError):
            analyze_retrieval_robustness(
                self.mandate, self.double,
                a.workbench.objectives, changed, a.retrieval,
                now=self.now, authorized=True,
            )

    def test_robustness_report_denies_unrecognized_objective_identity(self):
        a = self.atlas(self.source)
        original = a.retrieval.results[0]
        forged = replace(original, matched_objective_ids=("foreign-topic",))
        changed = replace(a.retrieval, results=(forged,))
        with self.assertRaises(PermissionError):
            analyze_retrieval_robustness(
                self.mandate, self.source,
                a.workbench.objectives, a.policies, changed,
                now=self.now, authorized=True,
            )

    def test_robustness_denies_forged_source_text_or_span(self):
        a = self.atlas(self.source)
        hit = a.retrieval.results[0]
        for changed in (
            replace(hit, text="This text was never captured"),
            replace(hit, passage_hash="f" * 64),
            replace(hit, start=hit.start + 1),
            replace(hit, end=10**9),
            replace(hit, source_hash="0" * 64),
            replace(hit, canonical_url="https://example.org/forged"),
        ):
            with self.subTest(change=changed):
                with self.assertRaises(PermissionError):
                    self.audit(self.source, replace(a, retrieval=replace(
                        a.retrieval, results=(changed,),
                    )))

    def test_robustness_denies_duplicate_selected_passages(self):
        a = self.atlas(self.source)
        forged = replace(a.retrieval, results=(a.retrieval.results[0],) * 2)
        with self.assertRaises(ValueError):
            self.audit(self.source, replace(a, retrieval=forged))

    def test_robustness_denies_repeated_objective_on_same_passage(self):
        a = self.atlas(self.source)
        hit = a.retrieval.results[0]
        forged = replace(hit, matched_objective_ids=(
            hit.matched_objective_ids[0], hit.matched_objective_ids[0],
        ))
        with self.assertRaises(ValueError):
            self.audit(self.source, replace(a, retrieval=replace(
                a.retrieval, results=(forged,),
            )))

    def test_robustness_denies_nonfinite_or_negative_ranking_score(self):
        a = self.atlas(self.source)
        for score in (-1, nan, inf):
            with self.subTest(score=score):
                changed = replace(a.retrieval.results[0], score=score)
                with self.assertRaises(ValueError):
                    self.audit(self.source, replace(a, retrieval=replace(
                        a.retrieval, results=(changed,),
                    )))

    def test_robustness_hard_caps_selected_passages_without_truncation(self):
        a = self.atlas(self.double)
        if len(a.retrieval.results) >= 2:
            with self.assertRaises(ValueError):
                self.audit(self.double, a, max_selected=1)
        else:
            with self.assertRaises(ValueError):
                self.audit(self.double, a, max_selected=0)

    def test_wrong_mandate_is_not_a_robustness_analysis_grant(self):
        a = self.atlas(self.source)
        other = replace(
            self.mandate,
            scope=replace(self.f.scope, owner_id="other-owner"),
        )
        with self.assertRaises(PermissionError):
            analyze_retrieval_robustness(
                other, self.source, a.workbench.objectives,
                a.policies, a.retrieval, now=self.now, authorized=True,
            )

    def test_exact_required_term_gate_applies_to_all_fusion_query_variants(self):
        from skeleton.ai.webcrawler.dragon_campaign_stack import ResearchObjective
        forced = ResearchObjective(
            "required-absent",
            "Which archive capture methods are described?",
            "method", "verification", .8, 1, 1, 3600,
            required_terms=("nonexistentmarker",),
        )
        a = compose_dragon_atlas(
            self.mandate, self.source,
            objectives=(forced,),
            source_policies=self.f.policies(self.source),
            policy_snapshot_authenticated=True,
            now=self.now, authorized=True,
        )
        self.assertEqual(a.retrieval.results, ())
        self.assertEqual(a.robustness.analyses[0].selected_passages, 0)
        self.assertEqual(a.robustness.analyses[0].host_ablation_risk,
                         "no_selected_evidence")
        self.assertTrue(all(
            "nonexistentmarker" in row.required_terms
            for row in a.lattice.queries
        ))

    def test_exact_required_term_gate_applies_to_all_bm25_query_variants(self):
        forced = ResearchObjective(
            "required-absent",
            "Which archive capture methods are described?",
            "method", "verification", .8, 1, 1, 3600,
            required_terms=("nonexistentmarker",),
        )
        a = compose_dragon_atlas(
            self.mandate, self.source,
            objectives=(forced,),
            source_policies=self.f.policies(self.source),
            policy_snapshot_authenticated=True,
            now=self.now, authorized=True,
            retrieval_mode="lexical_bm25",
        )
        self.assertEqual(a.retrieval.results, ())
        self.assertEqual(a.robustness.selected_passages, 0)
        self.assertIsNotNone(a.lexical_ranking)
        self.assertEqual(a.lexical_ranking.scored_passages, 0)

    def test_blocked_terms_prevent_passage_selection_even_if_query_matched(self):
        blocked = ResearchObjective(
            "blocked-archive",
            "Which archive capture methods are described?",
            "method", "verification", .8, 1, 1, 3600,
            blocked_terms=("archive",),
        )
        for mode in ("fusion", "lexical_bm25"):
            with self.subTest(mode=mode):
                a = compose_dragon_atlas(
                    self.mandate, self.source,
                    objectives=(blocked,),
                    source_policies=self.f.policies(self.source),
                    policy_snapshot_authenticated=True,
                    now=self.now, authorized=True,
                    retrieval_mode=mode,
                )
                self.assertEqual(a.retrieval.results, ())
                self.assertEqual(a.robustness.selected_passages, 0)

    def test_operator_terms_match_whole_tokens_not_substrings(self):
        from skeleton.ai.webcrawler.dragon_campaign_stack.query_lattice import (
            passage_matches_operator_terms,
        )
        self.assertTrue(passage_matches_operator_terms(
            "Methods use source-id and audit_log.", ("source-id",), (),
        ))
        self.assertTrue(passage_matches_operator_terms(
            "Methods use source-id and audit_log.", ("audit_log",), (),
        ))
        self.assertFalse(passage_matches_operator_terms(
            "Auditing protocols.", ("audit",), (),
        ))
        self.assertTrue(passage_matches_operator_terms(
            "Auditing protocols.", (), ("audit",),
        ))
        self.assertFalse(passage_matches_operator_terms(
            "Checking full audit_log.", (), ("audit_log",),
        ))
        self.assertTrue(passage_matches_operator_terms(
            "A source-id is not a source.", ("source-id",), (),
        ))

    def test_query_receipt_hard_filters_are_immutable_and_disjoint(self):
        from skeleton.ai.webcrawler.dragon_campaign_stack.query_lattice import (
            QueryVariant,
        )
        baseline = dict(
            objective_id="test-constraint", family="core", terms=("method",),
            query="method", priority=.8, weight=.7, ordinal=0,
        )
        with self.assertRaises(ValueError):
            QueryVariant(**baseline, required_terms=("same",),
                         blocked_terms=("same",))
        with self.assertRaises(ValueError):
            QueryVariant(**baseline, required_terms=("same", "same"))
        with self.assertRaises(ValueError):
            QueryVariant(**baseline, blocked_terms=("MixedCase",))
        with self.assertRaises(TypeError):
            QueryVariant(**baseline, required_terms=["not-a-tuple"])

    def test_one_objective_filter_does_not_suppress_other_valid_objective(self):
        valid = self.f.objective()
        blocked = ResearchObjective(
            "required-absent",
            "Which archive capture methods are described?",
            "method", "verification", .8, 1, 1, 3600,
            required_terms=("nonexistentmarker",),
        )
        for mode in ("fusion", "lexical_bm25"):
            with self.subTest(mode=mode):
                a = compose_dragon_atlas(
                    self.mandate, self.source,
                    objectives=(valid, blocked),
                    source_policies=self.f.policies(self.source),
                    policy_snapshot_authenticated=True,
                    now=self.now, authorized=True,
                    retrieval_mode=mode,
                )
                self.assertGreater(len(a.retrieval.results), 0)
                self.assertTrue(all(
                    "required-absent" not in hit.matched_objective_ids
                    for hit in a.retrieval.results
                ))
                mapped = {x.objective_id: x for x in a.robustness.analyses}
                self.assertEqual(mapped["required-absent"].selected_passages, 0)
                self.assertGreater(mapped["archive-method"].selected_passages, 0)

    def test_exact_same_content_on_two_hosts_is_not_two_independent_families(self):
        identical = fixtures.research_text("identical")
        captured = self.f.with_sources(
            ("https://example.com/archive", identical),
            ("https://example.org/research", identical),
        )
        a = self.atlas(captured)
        self.assertGreaterEqual(a.robustness.selected_sources, 1)
        observed_hashes = {x.source_hash for x in a.retrieval.results}
        self.assertEqual(len(observed_hashes), 1)
        self.assertEqual(a.robustness.distinct_content_families, 1)
        if a.robustness.selected_sources > 1:
            self.assertEqual(a.robustness.cross_host_exact_clone_groups, 1)
            self.assertEqual(len(a.robustness.exact_content_reuse), 1)
            clone = a.robustness.exact_content_reuse[0]
            self.assertTrue(clone.is_cross_host)
            self.assertEqual(len(clone.selected_source_ids), 2)
            self.assertEqual(clone.observed_hosts,
                             ("example.com", "example.org"))
            self.assertFalse(clone.independent_origin_verified)
            self.assertEqual(a.robustness.analyses[0].host_ablation_risk,
                             "same_content_on_multiple_hosts")
        self.assertFalse(a.robustness.verified_independence)

    def test_different_content_hashes_never_collide_as_exact_clones(self):
        a = self.atlas(self.double)
        expected = {hit.source_hash for hit in a.retrieval.results}
        self.assertEqual(a.robustness.distinct_content_families,
                         len(expected))
        self.assertFalse(any(
            group.content_sha256 not in expected
            for group in a.robustness.exact_content_reuse
        ))

    def test_host_ablation_reports_remaining_exact_content_families(self):
        a = self.atlas(self.double)
        for event in a.robustness.leave_one_host_out:
            remaining = {
                hit.source_hash for hit in a.retrieval.results
                if hit.host != event.removed_host
            }
            self.assertEqual(
                event.surviving_distinct_content_families, len(remaining),
            )

    def test_pairwise_objective_reuse_observes_content_hashes(self):
        a = self.multi(self.double)
        for reuse in a.robustness.objective_reuse:
            left = {hit.source_hash for hit in a.retrieval.results
                    if reuse.left_objective_id in hit.matched_objective_ids}
            right = {hit.source_hash for hit in a.retrieval.results
                     if reuse.right_objective_id in hit.matched_objective_ids}
            self.assertEqual(
                reuse.overlapping_content_hashes,
                tuple(sorted(left & right)),
            )
            self.assertFalse(reuse.evidentiary_independence_proven)

    def test_withdrawn_sources_cannot_survive_in_content_clone_projection(self):
        captured = self.f.with_sources(
            ("https://example.com/archive", fixtures.research_text("copy")),
            ("https://example.org/research", fixtures.research_text("copy")),
        )
        a = compose_dragon_atlas(
            self.mandate, captured,
            objectives=(self.f.objective(),),
            source_policies=self.f.policies(captured, status="withdrawn"),
            policy_snapshot_authenticated=True,
            now=self.now, authorized=True,
        )
        self.assertEqual(a.robustness.selected_sources, 0)
        self.assertEqual(a.robustness.exact_content_reuse, ())
        self.assertEqual(a.robustness.distinct_content_families, 0)

    def test_content_copy_groups_cannot_be_fabricated_after_receipt(self):
        a = self.atlas(self.double)
        forged = replace(
            a.robustness, cross_host_exact_clone_groups=1000,
        )
        with self.assertRaises(PermissionError):
            verify_dragon_atlas_trace(
                self.mandate, self.double,
                replace(a, robustness=forged), now=self.now, authorized=True,
            )

    def test_content_clone_metadata_never_contains_captured_bodies(self):
        a = self.atlas(self.double)
        for group in a.robustness.exact_content_reuse:
            self.assertEqual(len(group.content_sha256), 64)
            self.assertFalse(group.independent_origin_verified)
            self.assertFalse(hasattr(group, "text"))
            self.assertFalse(hasattr(group, "raw_html"))
            self.assertFalse(hasattr(group, "model_verdict"))

    def test_index_hard_filter_runs_before_top_one_window(self):
        from skeleton.ai.webcrawler.dragon_campaign_stack import (
            build_ephemeral_index, search_ephemeral_index,
        )
        text = " ".join(
            "Archive capture methodology and historical evidence. "
            + " ".join(f"independent{i}reference{j}" for j in range(32))
            + " Archive capture reference provenance."
            for i in range(5)
        ) + " Archive capture requiredneedle."
        captured = self.f.with_sources(
            ("https://example.com/archive", text),
        )
        index = build_ephemeral_index(
            self.mandate, captured, now=self.now,
            authorized=True,
        )
        broad = search_ephemeral_index(
            self.mandate, captured, index,
            "archive capture",
            now=self.now, authorized=True, mode="any", limit=1,
        )
        required = search_ephemeral_index(
            self.mandate, captured, index,
            "archive capture",
            now=self.now, authorized=True, mode="any", limit=1,
            required_terms=("requiredneedle",),
        )
        self.assertTrue(broad.hits)
        self.assertTrue(required.hits)
        self.assertIn("requiredneedle", required.hits[0].text.casefold())
        self.assertLessEqual(len(required.hits), 1)
        self.assertTrue(all(
            "requiredneedle" in hit.text.casefold() for hit in required.hits
        ))

    def test_index_rejects_contradictory_or_unnormalized_hard_filters(self):
        from skeleton.ai.webcrawler.dragon_campaign_stack import (
            build_ephemeral_index, search_ephemeral_index,
        )
        index = build_ephemeral_index(
            self.mandate, self.source, now=self.now,
            authorized=True,
        )
        for arguments in (
            {"required_terms": ("same",), "blocked_terms": ("same",)},
            {"required_terms": ("MixedCase",)},
            {"blocked_terms": ("a",)},
            {"required_terms": ["mutable"]},
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises((ValueError, TypeError)):
                    search_ephemeral_index(
                        self.mandate, self.source, index,
                        "archive capture",
                        now=self.now, authorized=True, **arguments,
                    )

    def test_preselected_filtered_query_has_distinct_replay_digest(self):
        from skeleton.ai.webcrawler.dragon_campaign_stack import (
            build_ephemeral_index, search_ephemeral_index,
        )
        index = build_ephemeral_index(
            self.mandate, self.source, now=self.now,
            authorized=True,
        )
        plain = search_ephemeral_index(
            self.mandate, self.source, index, "archive capture",
            now=self.now, authorized=True,
        )
        restricted = search_ephemeral_index(
            self.mandate, self.source, index, "archive capture",
            now=self.now, authorized=True,
            required_terms=("archive",),
        )
        self.assertNotEqual(plain.result_digest, restricted.result_digest)
        self.assertTrue(all("archive" in x.text.casefold()
                            for x in restricted.hits))

    def test_preselection_filter_cannot_admit_a_revoked_source(self):
        from skeleton.ai.webcrawler.dragon_campaign_stack import (
            build_ephemeral_index, search_ephemeral_index,
        )
        source_id = next(iter(self.source["sources"]))
        index = build_ephemeral_index(
            self.mandate, self.source, now=self.now,
            authorized=True, revoked_source_ids=(source_id,),
        )
        self.assertFalse(index.passages)
        blocked = search_ephemeral_index(
            self.mandate, self.source, index, "archive capture",
            now=self.now, authorized=True,
            revoked_source_ids=(source_id,),
            required_terms=("archive",),
        )
        self.assertFalse(blocked.hits)

    def test_index_search_denies_forged_passage_hash_span_or_terms(self):
        from skeleton.ai.webcrawler.dragon_campaign_stack import (
            build_ephemeral_index, search_ephemeral_index,
        )
        index = build_ephemeral_index(
            self.mandate, self.source, now=self.now, authorized=True,
        )
        self.assertTrue(index.passages)
        p = index.passages[0]
        bad_rows = (
            replace(p, passage_hash="f" * 64),
            replace(p, full_content_hash="f" * 64),
            replace(p, preserved_text_hash="f" * 64),
            replace(p, canonical_url="https://example.org/swap"),
            replace(p, start=-1),
            replace(p, start=True),
            replace(p, end=p.end + 10000),
            replace(p, terms=("fakeoperator",)),
            replace(p, text="forged source text"),
        )
        for item in bad_rows:
            with self.subTest(field=item):
                tampered = replace(index, passages=(item,))
                with self.assertRaises(PermissionError):
                    search_ephemeral_index(
                        self.mandate, self.source, tampered,
                        "archive capture", now=self.now, authorized=True,
                        mode="any",
                    )

    def test_canonical_passages_remain_searchable_after_strict_hash_validation(self):
        from skeleton.ai.webcrawler.dragon_campaign_stack import (
            build_ephemeral_index, search_ephemeral_index,
        )
        index = build_ephemeral_index(
            self.mandate, self.source, now=self.now,
            authorized=True,
        )
        result = search_ephemeral_index(
            self.mandate, self.source, index,
            "archive capture", now=self.now, authorized=True,
            mode="any", limit=8,
        )
        self.assertTrue(result.hits)
        source = next(iter(self.source["sources"].values()))
        from hashlib import sha256
        for hit in result.hits:
            self.assertEqual(
                sha256(source["text"][hit.start:hit.end].encode("utf-8")).hexdigest(),
                hit.passage_hash,
            )
            self.assertEqual(hit.canonical_url, source["canonical_url"])

    def test_all_analysis_outputs_retain_explicit_no_authority_flags(self):
        a = self.atlas(self.double)
        r = a.robustness
        self.assertFalse(r.training_authorized)
        self.assertFalse(r.publication_authorized)
        self.assertFalse(r.counterfactual_ranking_executed)
        self.assertFalse(r.verified_independence)
        self.assertTrue(r.source_bodies_excluded)
        self.assertTrue(all(x.hypothetical_selection_only
                            for x in r.leave_one_host_out))
        self.assertTrue(all(not x.reranking_executed
                            for x in r.leave_one_host_out))


if __name__ == "__main__":
    unittest.main()
