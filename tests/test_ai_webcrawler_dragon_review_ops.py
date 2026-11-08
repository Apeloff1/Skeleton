"""Dragon review operations end-to-end source-only qualification.

Scenarios exercise canonical CrawlRun fixtures, multiple policy states,
human review dependency replay, citation custody, model handoff metadata,
finite work budgets and tamper-evident trace boundaries.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import unittest

import test_ai_webcrawler_dragon_atlas as samples

from skeleton.ai.webcrawler.dragon_campaign_stack import (
    ReviewEffort, HumanReviewAction, HumanReviewProposal,
    assemble_evidence_graph, compile_review_agenda, replay_human_reviews,
    next_review_action, compile_research_handoff,
    verify_research_handoff, allocate_human_review, build_citation_manifest,
    verify_citation_manifest, compose_dragon_atlas,
    SourceLink, SourcePolicyDecision, project_source_policy,
    verify_dragon_atlas_trace,
)


class DragonReviewOperationsTest(unittest.TestCase):
    def setUp(self):
        self.f = samples.DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid"
        )
        self.f.setUp()
        self.source = self.f.with_sources(
            ("https://example.com/archive", samples.research_text("operations"))
        )
        self.atlas = self.f.atlas(self.source)
        self.now = self.f.now + 3
        self.first_id = next(iter(self.source["sources"]))

    def held_atlas(self):
        return compose_dragon_atlas(
            self.f.mandate, self.source,
            objectives=(self.f.objective(),),
            source_policies=self.f.policies(self.source, status="withdrawn"),
            policy_snapshot_authenticated=True,
            now=self.now, authorized=True,
        )

    def review_action(self, task, *, sequence=1, prior=None, action="reviewed",
                      agenda=None, policy=None, expected_revision=0):
        ag = agenda or self.atlas.agenda
        pol = policy or self.atlas.policies
        return HumanReviewAction(
            task_id=task.task_id, action=action,
            reviewer_id="backend-authenticated-human-actor",
            external_receipt="review-ledger-external-authority",
            reviewed_at=self.now,
            sequence=sequence,
            expected_task_revision=expected_revision,
            prior_chain_digest=prior or "0" * 64,
            agenda_digest=ag.agenda_digest, policy_digest=pol.policy_digest,
            signature_verified_by_authority=True,
        )

    def effort(self, agenda=None, minutes=12):
        ag = agenda or self.atlas.agenda
        return tuple(ReviewEffort(kind, minutes, "operator_estimate")
                     for kind in sorted({x.task_type for x in ag.tasks}))

    def test_integrated_six_operational_stage_chain(self):
        atlas = self.atlas
        self.assertEqual(len(atlas.stages), 26)
        self.assertEqual(atlas.stages[10].name, "policy_bound_evidence_graph")
        self.assertEqual(atlas.stages[11].name, "dependency_review_agenda")
        self.assertEqual(atlas.stages[12].name, "append_only_review_projection")
        self.assertEqual(atlas.stages[13].name, "least_authority_jeeves_handoff")
        self.assertEqual(atlas.stages[14].name, "optional_human_review_portfolio")
        self.assertEqual(atlas.stages[15].name, "exact_span_citation_manifest")
        verify_dragon_atlas_trace(
            self.f.mandate, self.source, atlas, now=self.now, authorized=True,
        )

    def test_evidence_graph_vertices_have_no_raw_passage_bodies(self):
        graph = self.atlas.graph
        self.assertEqual(graph.integrity.source_count, 1)
        self.assertGreater(graph.integrity.passage_count, 0)
        self.assertTrue(all(node.review_required for node in graph.vertices))
        self.assertFalse(graph.may_publish)
        self.assertFalse(graph.may_execute_network)
        self.assertNotIn("Archive capture methodology", repr(graph.vertices))

    def test_source_passage_objective_arcs_are_anchored(self):
        graph = self.atlas.graph
        self.assertTrue(any(x.relation == "contains_passage" for x in graph.arcs))
        self.assertTrue(any(x.relation == "matches_objective" for x in graph.arcs))
        self.assertTrue(all(not x.accepted_for_truth for x in graph.arcs))
        self.assertTrue(graph.objectives[0].distinct_source_ids)
        self.assertTrue(graph.objectives[0].distinct_hosts)

    def test_empty_crawl_has_only_operator_objective_and_review_gap(self):
        empty = self.f.atlas(self.f.empty)
        self.assertEqual(empty.graph.integrity.source_count, 0)
        self.assertEqual(empty.graph.integrity.passage_count, 0)
        self.assertEqual(empty.citations.citations, ())
        self.assertTrue(any(x.task_type == "objective_gap"
                            for x in empty.agenda.tasks))
        self.assertFalse(empty.handoff.source_text_included)

    def test_withdrawn_source_excluded_from_graph_citations_and_handoff(self):
        atlas = self.held_atlas()
        self.assertEqual(atlas.graph.integrity.passage_count, 0)
        self.assertEqual(atlas.citations.citations, ())
        self.assertEqual(atlas.handoff.citations, ())
        self.assertIn(self.first_id, atlas.graph.tainted_source_ids)
        self.assertTrue(any(x.task_type == "source_policy"
                            for x in atlas.agenda.tasks))
        self.assertFalse(atlas.publication_authorized)

    def test_graph_denies_foreign_policy_revision(self):
        policy = replace(self.atlas.policies, source_snapshot_digest="e"*64)
        with self.assertRaises(PermissionError):
            assemble_evidence_graph(
                self.f.mandate, self.source, policy,
                self.atlas.workbench.objectives,
                self.atlas.index, self.atlas.retrieval,
                now=self.now, authorized=True,
            )

    def test_graph_denies_wrong_index_receipt(self):
        index = replace(self.atlas.index, index_digest="e"*64)
        with self.assertRaises(PermissionError):
            assemble_evidence_graph(
                self.f.mandate, self.source, self.atlas.policies,
                self.atlas.workbench.objectives, index,
                self.atlas.retrieval,
                now=self.now, authorized=True,
            )

    def test_graph_cannot_exceed_explicit_capacity(self):
        with self.assertRaises(ValueError):
            assemble_evidence_graph(
                self.f.mandate, self.source, self.atlas.policies,
                self.atlas.workbench.objectives,
                self.atlas.index, self.atlas.retrieval,
                now=self.now, authorized=True, max_vertices=1,
            )

    def test_graph_denies_unattested_lineage_taint_of_allowed_capture(self):
        src = self.f.with_sources(
            ("https://example.com/archive", samples.research_text("hold")),
            ("https://example.org/research", samples.research_text("child")),
        )
        ids = sorted(src["sources"])
        policy = tuple(
            replace(row, status="withdrawn") if row.source_id == ids[0] else row
            for row in self.f.policies(src)
        )
        # A retained source downstream of an already withdrawn parent may
        # never become a safe graph retrieval hit without further policy.
        with self.assertRaises(PermissionError):
            compose_dragon_atlas(
                self.f.mandate, src, objectives=(self.f.objective(),),
                source_policies=policy,
                policy_snapshot_authenticated=True,
                source_links=(SourceLink(ids[1], ids[0], "derived_from"),),
                now=self.now, authorized=True,
            )

    def test_review_agenda_deterministic_and_unique(self):
        a = self.atlas.agenda
        second = compile_review_agenda(
            self.f.mandate, self.atlas.graph,
            self.atlas.policies, self.atlas.retrieval,
            self.atlas.workbench.coverage, now=self.now,
            authorized=True,
        )
        self.assertEqual(a.agenda_digest, second.agenda_digest)
        self.assertEqual(len({x.task_id for x in a.tasks}), len(a.tasks))
        self.assertTrue(a.ready_task_ids)
        self.assertTrue(all(not x.externally_executable for x in a.tasks))

    def test_review_agenda_rejects_foreign_graph(self):
        altered = replace(self.atlas.graph, source_snapshot_digest="e"*64)
        with self.assertRaises(PermissionError):
            compile_review_agenda(
                self.f.mandate, altered, self.atlas.policies,
                self.atlas.retrieval, self.atlas.workbench.coverage,
                now=self.now, authorized=True,
            )

    def test_review_replay_empty_has_no_fake_operator_reviews(self):
        replay = self.atlas.review_replay
        self.assertEqual(replay.event_count, 0)
        self.assertEqual(replay.complete_task_ids, ())
        self.assertFalse(replay.facts_verified)
        self.assertFalse(replay.persistent_write_performed)

    def test_review_action_requires_actual_authenticated_authority(self):
        task = next(x for x in self.atlas.agenda.tasks if not x.predecessors)
        with self.assertRaises(PermissionError):
            replace(self.review_action(task), signature_verified_by_authority=False)

    def test_root_task_can_be_recorded_but_never_publish(self):
        task = next(x for x in self.atlas.agenda.tasks if not x.predecessors)
        action = self.review_action(task)
        state = replay_human_reviews(
            self.f.mandate, self.atlas.agenda, self.atlas.policies,
            (action,), now=self.now, authorized=True,
        )
        self.assertIn(task.task_id, state.complete_task_ids)
        self.assertNotEqual(state.chain_head, "0"*64)
        self.assertFalse(state.facts_verified)
        self.assertFalse(state.review_signature_authentication_proven_by_receipt)

    def test_dependency_cannot_be_completed_before_prerequisites(self):
        dependent = next(x for x in self.atlas.agenda.tasks if x.predecessors)
        with self.assertRaises(PermissionError):
            replay_human_reviews(
                self.f.mandate, self.atlas.agenda, self.atlas.policies,
                (self.review_action(dependent),),
                now=self.now, authorized=True,
            )

    def test_review_replay_rejects_chain_forgery(self):
        task = next(x for x in self.atlas.agenda.tasks if not x.predecessors)
        with self.assertRaises(PermissionError):
            replay_human_reviews(
                self.f.mandate, self.atlas.agenda, self.atlas.policies,
                (replace(self.review_action(task), prior_chain_digest="b"*64),),
                now=self.now, authorized=True,
            )

    def test_review_replay_rejects_sequence_gap(self):
        task = next(x for x in self.atlas.agenda.tasks if not x.predecessors)
        with self.assertRaises(ValueError):
            replay_human_reviews(
                self.f.mandate, self.atlas.agenda, self.atlas.policies,
                (self.review_action(task, sequence=2),),
                now=self.now, authorized=True,
            )

    def test_review_replay_rejects_task_revision_conflict(self):
        task = next(x for x in self.atlas.agenda.tasks if not x.predecessors)
        with self.assertRaises(PermissionError):
            replay_human_reviews(
                self.f.mandate, self.atlas.agenda, self.atlas.policies,
                (self.review_action(task, expected_revision=1),),
                now=self.now, authorized=True,
            )

    def test_review_replay_denies_source_withdrawal_reviewed_transition(self):
        atlas = self.held_atlas()
        task = next(x for x in atlas.agenda.tasks
                    if x.task_type == "source_policy")
        with self.assertRaises(PermissionError):
            replay_human_reviews(
                self.f.mandate, atlas.agenda, atlas.policies,
                (self.review_action(task, agenda=atlas.agenda,
                                    policy=atlas.policies),),
                now=self.now, authorized=True,
            )

    def test_review_proposal_does_not_fabricate_review_receipt(self):
        task_id = self.atlas.review_replay.pending_task_ids[0]
        proposed = next_review_action(
            self.atlas.agenda, self.atlas.policies,
            self.atlas.review_replay,
            task_id=task_id, action="needs_evidence", now=self.now,
        )
        self.assertIsInstance(proposed, HumanReviewProposal)
        self.assertFalse(proposed.authenticated)
        self.assertFalse(proposed.persistence_performed)

    def test_review_proposal_denies_unknown_task(self):
        with self.assertRaises(ValueError):
            next_review_action(
                self.atlas.agenda, self.atlas.policies, self.atlas.review_replay,
                task_id="unknown-queue-task", action="deferred", now=self.now,
            )

    def test_review_portfolio_requires_operator_effort_estimates(self):
        with self.assertRaises(ValueError):
            allocate_human_review(
                self.f.mandate, self.atlas.agenda, (),
                now=self.now, authorized=True,
            )

    def test_review_portfolio_budget_and_dependency_fencing(self):
        result = allocate_human_review(
            self.f.mandate, self.atlas.agenda, self.effort(),
            replay=self.atlas.review_replay, now=self.now,
            authorized=True, budget_minutes=72,
        )
        self.assertLessEqual(result.consumed_minutes_estimated, 72)
        self.assertEqual(
            result.remaining_minutes_estimated +
            result.consumed_minutes_estimated, 72,
        )
        self.assertTrue(all(x.binding == "operator_review_proposal_only"
                            for x in result.tasks_selected))
        self.assertFalse(result.assignments_persisted)
        order = {x.task_id: x.assigned_order for x in result.tasks_selected}
        for row in result.tasks_selected:
            for requirement in row.prerequisites_scheduled:
                self.assertLess(order[requirement], row.assigned_order)

    def test_review_portfolio_bounded_capacity_and_fairness(self):
        p = allocate_human_review(
            self.f.mandate, self.atlas.agenda, self.effort(),
            now=self.now, authorized=True,
            max_assignments=1, max_per_objective=1,
        )
        self.assertLessEqual(len(p.tasks_selected), 1)
        self.assertLessEqual(sum(x[1] for x in p.objective_coverage), 1)

    def test_review_portfolio_no_fake_observed_cost(self):
        p = allocate_human_review(
            self.f.mandate, self.atlas.agenda, self.effort(),
            now=self.now, authorized=True,
        )
        self.assertFalse(p.actual_effort_measured)
        self.assertTrue(all(x.estimate_basis == "operator_estimate"
                            for x in p.tasks_selected))

    def test_review_portfolio_requires_all_task_type_estimates(self):
        with self.assertRaises(ValueError):
            allocate_human_review(
                self.f.mandate, self.atlas.agenda,
                (ReviewEffort("objective_gap", 10, "operator_estimate"),),
                now=self.now, authorized=True,
            )

    def test_review_portfolio_excludes_reviewed_task(self):
        root = next(x for x in self.atlas.agenda.tasks if not x.predecessors)
        replay = replay_human_reviews(
            self.f.mandate, self.atlas.agenda, self.atlas.policies,
            (self.review_action(root),),
            now=self.now, authorized=True,
        )
        p = allocate_human_review(
            self.f.mandate, self.atlas.agenda, self.effort(),
            replay=replay, now=self.now, authorized=True,
        )
        self.assertTrue(all(x.task_id != root.task_id for x in p.tasks_selected))

    def test_pipeline_portfolio_requires_supplied_effort(self):
        atlas = self.f.atlas(
            self.source, review_effort=self.effort(),
            review_budget_minutes=120,
        )
        self.assertIsNotNone(atlas.portfolio)
        self.assertLessEqual(atlas.portfolio.consumed_minutes_estimated, 120)
        verify_dragon_atlas_trace(
            self.f.mandate, self.source, atlas, now=self.now, authorized=True,
        )

    def test_jeeves_handoff_contains_no_external_body(self):
        handoff = self.atlas.handoff
        self.assertFalse(handoff.source_text_included)
        self.assertFalse(handoff.local_model_invoked)
        self.assertFalse(handoff.remote_model_invoked)
        self.assertFalse(handoff.task_execution_authorized)
        self.assertNotIn("Archive capture methodology", handoff.serialized_json)
        parsed = json.loads(handoff.serialized_json)
        self.assertFalse(parsed["execution_authorized"])
        self.assertFalse(parsed["training_authorized"])
        self.assertTrue(parsed["refetch_authority_before_any_source_use"])
        verify_research_handoff(
            self.f.mandate, self.atlas.policies,
            self.atlas.graph, self.atlas.retrieval,
            self.atlas.agenda, handoff,
            now=self.now, authorized=True, replay=self.atlas.review_replay,
        )

    def test_jeeves_handoff_modified_digest_rejected(self):
        with self.assertRaises(ValueError):
            verify_research_handoff(
                self.f.mandate, self.atlas.policies, self.atlas.graph,
                self.atlas.retrieval, self.atlas.agenda,
                replace(self.atlas.handoff, handoff_digest="f"*64),
                now=self.now, authorized=True, replay=self.atlas.review_replay,
            )

    def test_jeeves_handoff_claimed_model_execution_rejected(self):
        with self.assertRaises(PermissionError):
            verify_research_handoff(
                self.f.mandate, self.atlas.policies, self.atlas.graph,
                self.atlas.retrieval, self.atlas.agenda,
                replace(self.atlas.handoff, remote_model_invoked=True),
                now=self.now, authorized=True, replay=self.atlas.review_replay,
            )

    def test_jeeves_handoff_wrong_policy_rejected(self):
        with self.assertRaises(PermissionError):
            compile_research_handoff(
                self.f.mandate,
                replace(self.atlas.policies, policy_digest="f"*64),
                self.atlas.graph, self.atlas.retrieval,
                self.atlas.agenda, now=self.now, authorized=True,
            )

    def test_citation_manifest_has_exact_anchored_source_hashes(self):
        manifest = self.atlas.citations
        self.assertEqual(manifest.admitted, len(self.atlas.retrieval.results))
        self.assertFalse(manifest.publishable)
        self.assertFalse(manifest.source_text_retained_in_manifest)
        self.assertNotIn("Archive capture methodology", manifest.serialized_json)
        self.assertTrue(all(x.source_policy_current_at_issuance for x in manifest.citations))
        for ref in manifest.citations:
            captured = self.source["sources"][ref.source_id]
            self.assertEqual(
                sha256(captured["text"][ref.start:ref.end].encode("utf-8")).hexdigest(),
                ref.passage_hash,
            )
            self.assertEqual(captured["content_hash"], ref.full_content_hash)
        verify_citation_manifest(
            self.f.mandate, self.source,
            self.atlas.policies, self.atlas.retrieval, manifest,
            now=self.now, authorized=True,
            max_citations=manifest.max_citations,
            max_serialized_bytes=manifest.max_serialized_bytes,
        )

    def test_citation_manifest_tampered_source_hash_rejected(self):
        manifest = self.atlas.citations
        edited = replace(
            manifest,
            citations=(replace(manifest.citations[0], full_content_hash="a"*64),)
            + manifest.citations[1:],
        )
        with self.assertRaises(PermissionError):
            verify_citation_manifest(
                self.f.mandate, self.source,
                self.atlas.policies, self.atlas.retrieval, edited,
                now=self.now, authorized=True,
                max_citations=manifest.max_citations,
                max_serialized_bytes=manifest.max_serialized_bytes,
            )

    def test_citation_manifest_forbids_tampered_snapshot(self):
        alternate = self.f.with_sources(
            ("https://example.org/research", samples.research_text("other"))
        )
        with self.assertRaises(PermissionError):
            verify_citation_manifest(
                self.f.mandate, alternate,
                self.atlas.policies, self.atlas.retrieval, self.atlas.citations,
                now=self.now, authorized=True,
                max_citations=self.atlas.citations.max_citations,
            )

    def test_graph_integrity_score_not_publication(self):
        self.assertFalse(self.atlas.graph.integrity.knowledge_verified)
        self.assertFalse(self.atlas.review_replay.facts_verified)
        self.assertFalse(self.atlas.handoff.human_approval_present)
        self.assertFalse(self.atlas.citations.publishable)
        self.assertFalse(self.atlas.scorecard.verification_granted)


if __name__ == "__main__":
    unittest.main()
