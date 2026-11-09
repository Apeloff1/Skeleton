"""Dragon campaign advanced source-only qualification on canonical CrawlRun snapshots."""
from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256
import copy
import time
import unittest

from skeleton.ai.webcrawler.core import CrawlDocument, _source_score
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun
from skeleton.ai.webcrawler.research import EvidenceObservation
from skeleton.ai.webcrawler.dragon_campaign_stack.contracts import digest
from skeleton.ai.webcrawler.dragon_campaign_stack import (
    CampaignScope, CampaignLimits, CampaignMandate, CampaignJournal,
    ResearchObjective, compile_objectives, objective_matches,
    ResearchClaim, ClaimCitation, IndependenceAttestation, assess_claim_matrix,
    measure_objective_coverage,
    RetainedVersion, compare_retained_versions, build_temporal_sequence,
    NoveltyDocument, group_near_duplicates,
    analyze_frontier_topology, build_ephemeral_index, search_ephemeral_index,
    compile_crawl_risks, ResourceObservation, recommend_crawl_pressure,
    prioritize_unmet_research, create_review_packet, verify_review_packet,
    ReplayLink, audit_campaign_replay, inspect_crawl_campaign,
    verify_current_citations, decide_campaign_stop,
    CitationDependency, build_disagreement_graph, audit_robots_state,
    compose_dragon_workbench,
)


def sample_text(suffix: str = "a") -> str:
    return (
        "Archive capture methodology and historical evidence. "
        + " ".join(f"unique{suffix}{i}" for i in range(140))
        + " These archival records remain unreviewed research observations."
    )


class DeepCampaignTest(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.request = CrawlRequest(
            seed_urls=("https://example.com/archive", "https://example.org/research"),
            allowed_hosts=("example.com", "example.org"),
            query="archive capture", max_depth=2, max_requests=16,
            max_documents=8, max_response_bytes=4096, max_total_bytes=65536,
        )
        self.scope = CampaignScope(
            tenant_id="tenant-a", owner_id="owner-a",
            consent_id="consent-a", expires_at=self.now+3600,
            allowed_hosts=self.request.allowed_hosts, purpose="approved source research",
        )
        self.mandate = CampaignMandate(
            self.scope, self.request, self.request.query, self.now,
            CampaignLimits(max_candidates=32, max_dispatches=8,
                           max_per_host=4, max_evidence=32),
        )
        self.run = CrawlRun.create(
            self.request,
            scope={"tenant_id": "tenant-a", "owner_id": "owner-a"},
            consent={
                "consent_id": "consent-a", "capture_acknowledged": True,
                "source_rights_acknowledged": True,
                "expires_at": self.scope.expires_at,
            }, now=self.now,
        )
        self.snapshot = self.run.snapshot()

    def with_sources(self, *rows):
        """Build a complete valid capture snapshot; not merely forged source hashes."""
        state = copy.deepcopy(self.snapshot)
        state.pop("snapshot_digest")
        for url, text in rows:
            full = sha256(text.encode()).hexdigest()
            source_id = digest({"url": url, "content_hash": full})
            raw_hash = sha256(b"synthetic-http-body").hexdigest()
            provenance = {
                "schema": "skeleton.ai.crawl.provenance.v1",
                "canonical_url": url, "fetched_url": url, "fetched_at": self.now,
                "status": 200, "content_hash": full,
                "raw_body_hash": raw_hash,
                "binding_digest": digest(state["binding"]),
                "consent_id": self.scope.consent_id,
                "source_status": "unreviewed_external_capture",
                "training_permission": False, "raw_bytes_retained": False,
            }
            document = CrawlDocument(
                canonical_url=url, fetched_url=url,
                title="Source fixture", text=text,
                content_type="text/plain", content_hash=full,
                fetched_at=self.now,
                source_score=_source_score(url, text, 200),
                provenance=provenance, links=(),
            )
            state["sources"][source_id] = {
                "source_id": source_id, "canonical_url": url,
                "fetched_url": url, "title": "Source fixture",
                "text": text, "content_hash": full,
                "raw_body_hash": raw_hash, "preserved_text_hash": full,
                "text_truncated": False, "content_type": "text/plain",
                "fetched_at": self.now, "review_state": "unreviewed",
                "provenance": provenance,
                "observation": asdict(EvidenceObservation.from_document(
                    document, self.request.query,
                )),
            }
        state["usage"]["documents"] = len(state["sources"])
        state["snapshot_digest"] = digest(state)
        CrawlRun.from_snapshot(state)
        return state

    def inspect(self, snapshot=None, revoked=()):
        return inspect_crawl_campaign(
            snapshot or self.snapshot, self.mandate,
            now=self.now+2, authorized=True, revoked_source_ids=revoked,
        )

    def objective(self):
        return ResearchObjective(
            "archive-method", "How was archive capture methodology documented?",
            "method", "verification", 0.9, 1, 1, 3600,
            required_terms=("archive", "capture"),
        )

    def verified(self):
        snapshot = self.with_sources(
            ("https://example.com/archive", sample_text()),
        )
        report = self.inspect(snapshot)
        checks = verify_current_citations(
            self.mandate, snapshot, report.evidence.passages,
            now=self.now+2, authorized=True,
        )
        return snapshot, report, checks

    def test_structural_source_replay_and_valid_current_citations(self):
        snapshot, report, checks = self.verified()
        self.assertEqual(report.evidence.rejected_sources, ())
        self.assertGreater(len(report.evidence.passages), 0)
        self.assertTrue(all(x.valid_for_review for x in checks.entries))
        self.assertFalse(checks.knowledge_publication_authorized)
        self.assertEqual(snapshot["usage"]["documents"], 1)

    def test_objective_order_and_invalid_capacities(self):
        first = self.objective()
        second = replace(first, objective_id="other-objective", priority=0.2)
        plan = compile_objectives(
            self.mandate, (second, first), now=self.now+1, authorized=True,
        )
        self.assertEqual(plan.objectives, (first, second))
        self.assertFalse(plan.authorized_to_acquire)
        self.assertTrue(objective_matches(first, sample_text()))
        self.assertFalse(objective_matches(first, "miscellaneous unrelated text"))
        with self.assertRaises(ValueError):
            compile_objectives(
                self.mandate, (first, first), now=self.now+1, authorized=True,
            )

    def test_claim_matrix_requires_exact_passage_check(self):
        _, report, checks = self.verified()
        claim = ResearchClaim(
            "claim-archive", "Original source mentions archive methods",
            "archive-method",
        )
        p = report.evidence.passages[0]
        citation = ClaimCitation(
            claim.claim_id, p.source_id, p.passage_hash,
            "supports", 0.95, "Attributed passage in source",
        )
        matrix = assess_claim_matrix(
            self.mandate, (claim,), (citation,),
            report.evidence.passages, checks,
            (IndependenceAttestation(
                "group-one", (p.source_id,), "operator-review-ref", True,
            ),),
            now=self.now+2, authorized=True,
        )
        self.assertEqual(matrix.claims[0].attested_support_groups, 1)
        self.assertEqual(matrix.claims[0].support_triage_score, 0.95)
        self.assertFalse(matrix.claims[0].verified_fact)
        self.assertFalse(matrix.authorized_for_publication)
        with self.assertRaises(PermissionError):
            assess_claim_matrix(
                self.mandate, (claim,), (citation,), report.evidence.passages,
                replace(checks, entries=()),
                now=self.now+2, authorized=True,
            )

    def test_objective_coverage_requires_human_review(self):
        _, report, checks = self.verified()
        plan = compile_objectives(
            self.mandate, (self.objective(),),
            now=self.now+2, authorized=True,
        )
        coverage = measure_objective_coverage(
            self.mandate, plan, report.evidence, checks,
            now=self.now+2, authorized=True,
        )
        self.assertTrue(coverage.objectives[0].blocked)
        self.assertGreaterEqual(coverage.objectives[0].reviewable_passages, 1)
        self.assertEqual(
            coverage.objectives[0].next_action,
            "obtain_and_review_independent_source_provenance",
        )

    def test_linear_unicode_temporal_diff_and_partial_hold(self):
        url = "https://example.com/archive"
        old, new = "A 🐉 story was old.", "A 🐉 story is new."
        a, b = sha256(old.encode()).hexdigest(), sha256(new.encode()).hexdigest()
        earlier = RetainedVersion(
            digest({"url": url, "content_hash": a}), url,
            a, a, self.now, old, False,
        )
        later = RetainedVersion(
            digest({"url": url, "content_hash": b}), url,
            b, b, self.now+10, new, False,
        )
        comparison = compare_retained_versions(earlier, later)
        span = comparison.spans[0]
        self.assertEqual(old[span.before_start:span.before_end], "was old")
        self.assertEqual(new[span.after_start:span.after_end], "is new")
        self.assertEqual(build_temporal_sequence((earlier, later)).versions, 2)
        self.assertTrue(compare_retained_versions(
            earlier, replace(earlier, captured_at=self.now+10, truncated=True),
        ).requires_new_review)
        with self.assertRaises(ValueError):
            replace(earlier, source_id="f"*64)

    def test_novelty_groups_mirror_sources_without_independence(self):
        text = sample_text()
        a = NoveltyDocument("a"*64, sha256(text.encode()).hexdigest(), text)
        b = NoveltyDocument("b"*64, sha256(text.encode()).hexdigest(), text)
        family = group_near_duplicates((a, b))
        self.assertEqual(family.unique_families, 1)
        self.assertFalse(family.independent_corroboration_established)
        self.assertTrue(family.flagged_pairs[0].same_preserved_text)
        with self.assertRaises(ValueError):
            group_near_duplicates((a, a))

    def test_host_frontier_and_robot_cache_audit(self):
        topology = analyze_frontier_topology(
            self.snapshot, self.mandate, now=self.now+2,
            authorized=True, saturation_threshold=1,
        )
        self.assertEqual(topology.frontier_count, 2)
        self.assertEqual(len(topology.saturated_hosts), 2)
        robot = audit_robots_state(
            self.snapshot, self.mandate, now=self.now+2, authorized=True,
        )
        self.assertEqual(robot.origin_count, 2)
        self.assertEqual(len(robot.never_fetched_origins), 2)
        self.assertFalse(robot.network_robots_admission_granted)

    def test_ephemeral_index_exact_span_and_revocation(self):
        snapshot, _, _ = self.verified()
        index = build_ephemeral_index(
            self.mandate, snapshot, now=self.now+2, authorized=True,
        )
        hits = search_ephemeral_index(
            self.mandate, snapshot, index, "archive capture",
            now=self.now+3, authorized=True,
        )
        self.assertGreater(len(hits.hits), 0)
        self.assertFalse(hits.publication_authorized)
        source = next(iter(snapshot["sources"]))
        for hit in hits.hits:
            self.assertEqual(snapshot["sources"][source]["text"][hit.start:hit.end], hit.text)
        denied = search_ephemeral_index(
            self.mandate, snapshot, index, "archive capture",
            now=self.now+3, authorized=True,
            revoked_source_ids=(source,),
        )
        self.assertEqual(denied.hits, ())
        with self.assertRaises(PermissionError):
            search_ephemeral_index(
                self.mandate, self.snapshot, index,
                "archive", now=self.now+3, authorized=True,
            )

    def test_risk_inspection_is_not_a_network_authority(self):
        report = compile_crawl_risks(
            self.snapshot, self.mandate, now=self.now+2, authorized=True,
        )
        self.assertEqual(report.events_retained, 0)
        self.assertEqual(report.risks, ())
        self.assertFalse(report.review_required)

    def test_pressure_requires_measured_fresh_telemetry(self):
        report = self.inspect()
        measured = ResourceObservation(
            at=self.now+1,
            memory_available_bytes=1024*1024*1024,
            memory_total_bytes=8*1024*1024*1024,
            disk_free_bytes=10**10, cpu_pressure=0.2,
            worker_count=2, active_fetches=1,
        )
        pressure = recommend_crawl_pressure(
            self.mandate, report.budget, (measured,),
            now=self.now+2, authorized=True,
        )
        self.assertEqual(pressure.pressure, "nominal")
        self.assertFalse(pressure.physical_capacity_certified)
        critical = recommend_crawl_pressure(
            self.mandate, report.budget,
            (replace(measured, disk_free_bytes=1),),
            now=self.now+2, authorized=True,
        )
        self.assertTrue(critical.recommend_pause)
        self.assertEqual(critical.recommend_max_slice_steps, 0)

    def test_mission_strategy_keeps_existing_frontier(self):
        report = self.inspect()
        objectives = compile_objectives(
            self.mandate, (self.objective(),),
            now=self.now+2, authorized=True,
        )
        current = verify_current_citations(
            self.mandate, self.snapshot, (),
            now=self.now+2, authorized=True,
        )
        coverage = measure_objective_coverage(
            self.mandate, objectives, report.evidence, current,
            now=self.now+2, authorized=True,
        )
        topology = analyze_frontier_topology(
            self.snapshot, self.mandate, now=self.now+2, authorized=True,
        )
        strategy = prioritize_unmet_research(
            self.mandate, objectives, coverage, topology,
            report.budget, now=self.now+2, authorized=True,
        )
        self.assertFalse(strategy.acquisition_authorized)
        self.assertTrue(all(
            item.url in self.request.seed_urls for item in strategy.candidates
        ))
        self.assertEqual(len(strategy.proposed_plan.dispatches), 2)

    def test_review_packet_checksum_and_exact_source(self):
        report = self.inspect()
        packet = create_review_packet(
            self.mandate, report, now=self.now+2, authorized=True,
        )
        verify_review_packet(
            self.mandate, self.snapshot, packet,
            now=self.now+3, authorized=True,
        )
        self.assertFalse(packet.publication_granted)
        with self.assertRaises(ValueError):
            verify_review_packet(
                self.mandate, self.snapshot,
                replace(packet, holds=()),
                now=self.now+3, authorized=True,
            )
        with self.assertRaises(PermissionError):
            verify_review_packet(
                self.mandate, self.snapshot, packet,
                now=self.now+3, authorized=False,
            )

    def test_replay_audit_does_not_replay_external_effects(self):
        report = self.inspect()
        packet = create_review_packet(
            self.mandate, report, now=self.now+2, authorized=True,
        )
        journal = CampaignJournal(self.mandate.fingerprint)
        replay = audit_campaign_replay(
            self.mandate, self.snapshot, journal, packet,
            now=self.now+3, authorized=True,
        )
        self.assertFalse(replay.physical_effects_replayed)
        self.assertFalse(replay.historical_mongo_commits_verified)

    def test_disagreement_graph_preserves_independent_review_hold(self):
        _, report, checks = self.verified()
        p = report.evidence.passages[0]
        claim = ResearchClaim(
            "claim-a", "One page reports a research finding", "archive-method",
        )
        matrix = assess_claim_matrix(
            self.mandate, (claim,),
            (ClaimCitation(
                "claim-a", p.source_id, p.passage_hash,
                "supports", 0.8, "source text",
            ),),
            report.evidence.passages, checks,
            now=self.now+2, authorized=True,
        )
        graph = build_disagreement_graph(matrix)
        self.assertEqual(graph.disagreements, ())
        self.assertFalse(graph.claims_resolved)
        with self.assertRaises(ValueError):
            build_disagreement_graph(matrix, dependencies=(
                CitationDependency(p.source_id, "b"*64, "mirrors"),
            ))

    def test_workbench_composes_every_canonical_inspection(self):
        snapshot, _, _ = self.verified()
        report = compose_dragon_workbench(
            self.mandate, snapshot, objectives=(self.objective(),),
            now=self.now+2, authorized=True,
        )
        self.assertEqual(report.source_snapshot_digest, snapshot["snapshot_digest"])
        self.assertEqual(report.review_packet.run_id, snapshot["run_id"])
        self.assertGreater(report.coverage.total_candidate_evidence, 0)
        self.assertFalse(report.public_knowledge_ready)
        self.assertFalse(report.auto_execution_authorized)
        with self.assertRaises(PermissionError):
            compose_dragon_workbench(
                self.mandate, snapshot, objectives=(self.objective(),),
                now=self.now+2, authorized=False,
            )

    def test_workbench_prevents_cross_objective_claims(self):
        claim = ResearchClaim(
            "claim-foreign", "Evidence", "objective-outside-campaign",
        )
        with self.assertRaises(PermissionError):
            compose_dragon_workbench(
                self.mandate, self.snapshot, objectives=(self.objective(),),
                claims=(claim,), now=self.now+2, authorized=True,
            )


if __name__ == "__main__":
    unittest.main()
