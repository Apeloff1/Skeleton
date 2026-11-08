"""Canonical Dragon frontier, hypothetical acquisition and recovery controls.

These are source-only tests against real immutable CrawlRun snapshots. They
never touch the network, Mongo, provider runtime, installed AI, or OS workers.
The tests explicitly distinguish simulated preflight from actual acquisition.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from collections import Counter
import copy
import unittest

import test_ai_webcrawler_dragon_atlas as fixtures
from skeleton.ai.webcrawler.operations import CrawlRun, _digest
from skeleton.ai.webcrawler.dragon_campaign_stack.frontier_route_map import (
    _nonrecursive_components, CanonicalRouteArc,
)
from skeleton.ai.webcrawler.dragon_campaign_stack import (
    ResourceObservation, recommend_crawl_pressure,
    project_canonical_routes, simulate_canonical_slice,
    analyze_dispatch_faults, project_budget, compose_dragon_atlas,
    verify_dragon_atlas_trace,
)


class FrontierOperationTests(unittest.TestCase):
    def setUp(self):
        f = fixtures.DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid"
        )
        f.setUp()
        self.f = f
        self.now = f.now + 3
        self.mandate = f.mandate
        self.snapshot = f.empty
        from skeleton.ai.webcrawler.dragon_campaign_stack import inspect_crawl_campaign
        self.report = inspect_crawl_campaign(
            self.snapshot, self.mandate,
            now=self.now, authorized=True,
        )
        self.routes = project_canonical_routes(
            self.mandate, self.snapshot, now=self.now, authorized=True,
        )
        self.budget = self.report.budget

    def fresh_pressure(self, budget=None, **changes):
        fields = {
            "at": self.f.now + 1,
            "memory_available_bytes": 1 << 30,
            "memory_total_bytes": 8 << 30,
            "disk_free_bytes": 10**10,
            "cpu_pressure": .1,
            "worker_count": 3,
            "active_fetches": 0,
        }
        fields.update(changes)
        return recommend_crawl_pressure(
            self.mandate, budget or self.budget,
            (ResourceObservation(**fields),),
            now=self.now, authorized=True,
        )

    def simulated(self, snapshot=None, *, pressure=None, budget=None,
                  routes=None, **settings):
        current = self.snapshot if snapshot is None else snapshot
        return simulate_canonical_slice(
            self.mandate, current,
            routes or self.routes, budget or self.budget,
            now=self.now, authorized=True,
            pressure=pressure, **settings,
        )

    def changed_snapshot(self, fn, snapshot=None):
        state = copy.deepcopy(snapshot if snapshot is not None else self.snapshot)
        state.pop("snapshot_digest")
        fn(state)
        state["snapshot_digest"] = _digest(state)
        CrawlRun.from_snapshot(state)
        return state

    def with_robots(self, robots_text, *, status=200, origin="https://example.com"):
        def change(state):
            raw = robots_text.encode()
            state["robots"][origin] = {
                "text": robots_text,
                "fetched_at": self.f.now,
                "status": status,
                "raw_body_hash": sha256(raw).hexdigest(),
                "pending_url": origin + "/robots.txt",
                "redirects": [],
            }
        return self.changed_snapshot(change)

    def budget_for(self, snapshot):
        from skeleton.ai.webcrawler.dragon_campaign_stack.contracts import CampaignMandate
        from skeleton.ai.webcrawler.dragon_campaign_stack.budget import project_budget
        from skeleton.ai.webcrawler.dragon_campaign_stack.integration import inspect_crawl_campaign
        return inspect_crawl_campaign(
            snapshot, self.mandate,
            now=self.now, authorized=True,
        ).budget

    def event_snapshot(self, kinds):
        run = CrawlRun.from_snapshot(self.snapshot)
        for kind in kinds:
            run._event(
                kind, now=self.f.now + 1,
                url="https://example.com/archive",
                reason="test-only-canonical-event",
            )
        return run.snapshot()

    def test_route_projection_has_canonical_seed_universe(self):
        self.assertEqual(len(self.routes.nodes), 2)
        self.assertEqual(self.routes.run_id, self.snapshot["run_id"])
        self.assertEqual(self.routes.source_snapshot_digest,
                         self.snapshot["snapshot_digest"])
        self.assertEqual({x.url for x in self.routes.nodes},
                         set(self.f.request.seed_urls))
        self.assertFalse(self.routes.runnable_now)

    def test_routes_do_not_claim_recovered_discarded_links(self):
        self.assertEqual(self.routes.edges, ())
        self.assertFalse(self.routes.unobserved_links_recovered)
        self.assertEqual(self.routes.unknown_parent_urls, ())
        self.assertEqual(self.routes.unreachable_pending_urls, ())

    def test_route_graph_has_one_component_per_isolated_seed(self):
        self.assertEqual(len(self.routes.strongly_connected_components), 2)
        self.assertTrue(all(len(x) == 1
                            for x in self.routes.strongly_connected_components))

    def test_route_host_pressure_uses_committed_pending_urls(self):
        self.assertEqual({x.host for x in self.routes.host_load},
                         {"example.com", "example.org"})
        self.assertEqual(sum(x.pending_urls for x in self.routes.host_load), 2)
        self.assertTrue(all(x.robots_status == "uncached"
                            for x in self.routes.host_load))
        self.assertTrue(all(x.pending_fairness_share == .5
                            for x in self.routes.host_load))

    def test_route_graph_never_implicitly_executes_network(self):
        self.assertFalse(self.routes.network_requests_started)
        self.assertTrue(all(not x.source_text_trusted for x in self.routes.nodes))
        self.assertTrue(all(not x.creates_network_authority
                            for x in self.routes.edges))

    def test_route_graph_deterministic_across_rebuilds(self):
        second = project_canonical_routes(
            self.mandate, self.snapshot,
            now=self.now, authorized=True,
        )
        self.assertEqual(second.route_digest, self.routes.route_digest)
        self.assertEqual(second.nodes, self.routes.nodes)

    def test_route_graph_disallows_excessive_nodes(self):
        with self.assertRaises(ValueError):
            project_canonical_routes(
                self.mandate, self.snapshot,
                now=self.now, authorized=True,
                max_nodes=1,
            )

    def test_route_graph_cannot_be_cross_tenant(self):
        altered = replace(
            self.mandate,
            scope=replace(self.f.scope, tenant_id="foreign-tenant"),
        )
        with self.assertRaises(PermissionError):
            project_canonical_routes(
                altered, self.snapshot, now=self.now, authorized=True,
            )

    def test_route_unknown_parent_is_reported_without_invented_links(self):
        parent = "https://example.com/unobserved"
        snap = self.changed_snapshot(
            lambda state: state["frontier"][0].update(parent_url=parent)
        )
        report = project_canonical_routes(
            self.mandate, snap, now=self.now, authorized=True,
        )
        self.assertIn(parent, report.unknown_parent_urls)
        self.assertTrue(any(x.parent_url == parent for x in report.edges))

    def test_route_report_detects_cross_host_parent_edges(self):
        parent = "https://example.org/research"
        snap = self.changed_snapshot(
            lambda state: state["frontier"][0].update(parent_url=parent)
        )
        report = project_canonical_routes(
            self.mandate, snap, now=self.now, authorized=True,
        )
        self.assertTrue(any(x.crosses_host_boundary for x in report.edges))

    def test_route_iterative_algorithm_detects_source_graph_cycle(self):
        seeds = tuple(x["url"] for x in self.snapshot["frontier"])
        def cycle(state):
            state["frontier"][0]["parent_url"] = seeds[1]
            state["frontier"][1]["parent_url"] = seeds[0]
        snap = self.changed_snapshot(cycle)
        report = project_canonical_routes(
            self.mandate, snap, now=self.now, authorized=True,
        )
        self.assertIn(tuple(sorted(seeds)), report.strongly_connected_components)
        self.assertEqual(len(report.edges), 2)

    def test_scc_converging_dag_cannot_fabricate_cycle(self):
        # A->B, A->C and B->C is a DAG with three singleton SCCs.
        # Earlier eager visited-child marking falsely grouped B and C.
        nodes = ("https://example.com/a", "https://example.com/b",
                 "https://example.com/c")
        arcs = (
            CanonicalRouteArc(nodes[0], nodes[1], False),
            CanonicalRouteArc(nodes[0], nodes[2], False),
            CanonicalRouteArc(nodes[1], nodes[2], False),
        )
        result = _nonrecursive_components(nodes, arcs)
        self.assertEqual(result, tuple((x,) for x in nodes))

    def test_scc_only_groups_actual_reciprocal_cycle(self):
        nodes = ("https://example.com/a", "https://example.com/b",
                 "https://example.com/c", "https://example.com/d")
        arcs = (
            CanonicalRouteArc(nodes[0], nodes[1], False),
            CanonicalRouteArc(nodes[0], nodes[2], False),
            CanonicalRouteArc(nodes[1], nodes[2], False),
            CanonicalRouteArc(nodes[2], nodes[1], False),
            CanonicalRouteArc(nodes[2], nodes[3], False),
        )
        result = _nonrecursive_components(nodes, arcs)
        self.assertEqual(result, ((nodes[0],), (nodes[1], nodes[2]), (nodes[3],)))

    def test_scc_iterative_long_dag_has_no_recursion_or_false_cycles(self):
        nodes = tuple(f"https://example.com/v{i:04d}" for i in range(800))
        arcs = tuple(CanonicalRouteArc(nodes[i], nodes[i + 1], False)
                     for i in range(len(nodes) - 1))
        result = _nonrecursive_components(nodes, arcs)
        self.assertEqual(len(result), len(nodes))
        self.assertEqual(result[0], (nodes[0],))
        self.assertEqual(result[-1], (nodes[-1],))

    def test_scc_rejects_dangling_or_attacker_supplied_endpoint(self):
        nodes = ("https://example.com/a",)
        with self.assertRaises(PermissionError):
            _nonrecursive_components(
                nodes, (CanonicalRouteArc(nodes[0], "https://unsafe.invalid/evil", True),),
            )

    def test_route_graph_does_not_allow_self_parent(self):
        url = self.snapshot["frontier"][0]["url"]
        snap = self.changed_snapshot(
            lambda state: state["frontier"][0].update(parent_url=url)
        )
        with self.assertRaises(ValueError):
            project_canonical_routes(
                self.mandate, snap, now=self.now, authorized=True,
            )

    def test_simulator_without_resource_evidence_has_zero_slots(self):
        p = self.simulated()
        self.assertEqual(p.steps, ())
        self.assertEqual(p.projected_byte_reserve, 0)
        self.assertIn("live_resource_telemetry_not_supplied", p.terminal_blockers)
        self.assertFalse(p.worker_lease_authenticated)
        self.assertFalse(p.reservation_committed)

    def test_nominal_simulation_models_only_robots_preflight(self):
        p = self.simulated(pressure=self.fresh_pressure())
        self.assertTrue(p.steps)
        self.assertTrue(all(x.action == "robots_preflight_only" for x in p.steps))
        self.assertTrue(all(x.requires_live_robots_authority for x in p.steps))
        self.assertTrue(all(not x.actual_network_executed for x in p.steps))
        self.assertFalse(p.actual_network_executed)

    def test_simulation_respects_bounded_physical_cap(self):
        p = self.simulated(pressure=self.fresh_pressure(), max_steps=1)
        self.assertLessEqual(len(p.steps), 1)
        self.assertLessEqual(p.projected_request_slots, 1)
        self.assertTrue(all(x.ordinal == i for i, x in enumerate(p.steps)))

    def test_simulation_does_not_refund_accounted_request_cap(self):
        p = self.simulated(pressure=self.fresh_pressure())
        self.assertEqual(
            p.request_budget_remaining_after + p.projected_request_slots,
            self.budget.requests_remaining,
        )
        self.assertEqual(
            p.byte_budget_remaining_after + p.projected_byte_reserve,
            self.budget.bytes_remaining,
        )

    def test_simulation_with_known_allow_robots_marks_page_only_as_candidate(self):
        snap = self.with_robots("User-agent: *\nAllow: /\n")
        budget = self.budget_for(snap)
        routes = project_canonical_routes(
            self.mandate, snap, now=self.now, authorized=True,
        )
        p = self.simulated(
            snap, routes=routes, budget=budget,
            pressure=self.fresh_pressure(budget),
        )
        self.assertTrue(any(x.action == "page_fetch_candidate"
                            for x in p.steps))
        self.assertFalse(p.reservation_committed)
        self.assertFalse(p.actual_network_executed)

    def test_simulation_with_known_disallow_robots_denies_page(self):
        snap = self.with_robots("User-agent: *\nDisallow: /\n")
        budget = self.budget_for(snap)
        routes = project_canonical_routes(
            self.mandate, snap, now=self.now, authorized=True,
        )
        p = self.simulated(
            snap, routes=routes, budget=budget,
            pressure=self.fresh_pressure(budget),
        )
        self.assertFalse(any(
            x.action == "page_fetch_candidate" and x.host == "example.com"
            for x in p.steps
        ))
        self.assertIn(
            "canonical_cached_robots_denied",
            {reason for _, reason in p.held_urls},
        )

    def test_simulation_preflight_cannot_assume_multiple_robots_authorities(self):
        snap = self.changed_snapshot(
            lambda state: state["frontier"].append({
                **copy.deepcopy(state["frontier"][0]),
                "url": "https://example.com/other",
                "original_url": "https://example.com/other",
            })
        )
        budget = self.budget_for(snap)
        routes = project_canonical_routes(
            self.mandate, snap, now=self.now, authorized=True,
        )
        p = self.simulated(
            snap, routes=routes, budget=budget,
            pressure=self.fresh_pressure(budget), max_steps=4,
        )
        checks = [x.origin for x in p.steps if x.action == "robots_preflight_only"]
        self.assertEqual(len(checks), len(set(checks)))
        self.assertEqual(checks.count("https://example.com"), 1)

    def test_simulation_resource_pressure_pauses_without_budget_expansion(self):
        stressed = self.fresh_pressure(
            memory_available_bytes=1, disk_free_bytes=1,
            cpu_pressure=1.0,
        )
        p = self.simulated(pressure=stressed)
        self.assertTrue(stressed.recommend_pause)
        self.assertEqual(p.steps, ())
        self.assertFalse(p.worker_lease_authenticated)

    def test_simulation_stale_resource_telemetry_pauses(self):
        report = self.fresh_pressure(at=self.f.now - 120)
        self.assertTrue(report.recommend_pause)
        self.assertEqual(self.simulated(pressure=report).steps, ())

    def test_simulator_refuses_cross_snapshot_route_receipt(self):
        snap = self.with_robots("User-agent: *\nAllow: /\n")
        with self.assertRaises(PermissionError):
            self.simulated(
                snap, pressure=self.fresh_pressure(),
            )

    def test_simulation_rejects_more_than_four_steps(self):
        with self.assertRaises(ValueError):
            self.simulated(pressure=self.fresh_pressure(), max_steps=5)

    def test_simulation_rejects_invalid_host_quota(self):
        with self.assertRaises(ValueError):
            self.simulated(pressure=self.fresh_pressure(), host_quota=0)

    def test_fault_ledger_empty_does_not_invent_healthy_real_network(self):
        f = analyze_dispatch_faults(
            self.mandate, self.snapshot, self.budget,
            now=self.now, authorized=True,
        )
        self.assertEqual(f.events_retained, 0)
        self.assertEqual(f.hosts, ())
        self.assertFalse(f.external_network_observed)
        self.assertFalse(f.mongo_commit_confirmed)
        self.assertFalse(f.budget_refunded)

    def test_fault_ledger_records_canonical_retry_and_transport_error(self):
        snap = self.event_snapshot(("retry", "error"))
        budget = self.budget_for(snap)
        ledger = analyze_dispatch_faults(
            self.mandate, snap, budget, now=self.now, authorized=True,
        )
        self.assertEqual(ledger.events_retained, 2)
        self.assertEqual(ledger.hosts[0].retries, 1)
        self.assertEqual(ledger.hosts[0].transport_failures, 1)
        self.assertTrue(any(
            x.code == "diagnose_transient_dns_socket_and_transport_failures"
            for x in ledger.recovery_queue
        ))
        self.assertTrue(all(not x.auto_execute for x in ledger.recovery_queue))

    def test_fault_ledger_flags_interrupted_remote_effect_without_refund(self):
        snap = self.event_snapshot(("interrupted_dispatch",))
        ledger = analyze_dispatch_faults(
            self.mandate, snap, self.budget_for(snap),
            now=self.now, authorized=True,
        )
        self.assertTrue(any(x.severity == "critical"
                            for x in ledger.recovery_queue))
        self.assertFalse(ledger.worker_join_confirmed)
        self.assertFalse(ledger.budget_refunded)

    def test_fault_ledger_emits_redirect_and_robots_custody(self):
        snap = self.event_snapshot(("robots", "redirect", "retry"))
        ledger = analyze_dispatch_faults(
            self.mandate, snap, self.budget_for(snap),
            now=self.now, authorized=True,
        )
        phases = {x.phase for x in ledger.phases}
        self.assertIn("robots_policy_observation", phases)
        self.assertIn("redirect_policy_observation", phases)
        self.assertIn("bounded_remote_retry", phases)

    def test_fault_ledger_rejects_cross_snapshot_budget_counters(self):
        snap = self.changed_snapshot(
            lambda state: state["usage"].update(requests=1)
        )
        with self.assertRaises(PermissionError):
            analyze_dispatch_faults(
                self.mandate, snap, self.budget,
                now=self.now, authorized=True,
            )

    def test_simulation_denies_forged_positive_remaining_requests(self):
        tampered = replace(
            self.budget,
            requests_remaining=self.budget.requests_remaining + 100,
        )
        with self.assertRaises(PermissionError):
            self.simulated(pressure=self.fresh_pressure(), budget=tampered)

    def test_simulation_denies_forged_document_and_byte_budgets(self):
        for change in (
            {"documents_remaining": self.budget.documents_remaining + 1},
            {"bytes_remaining": self.budget.bytes_remaining + 1024},
            {"snapshot_bytes": 1},
            {"blockers": () if self.budget.blockers else ("fake",)},
        ):
            with self.subTest(change=change):
                with self.assertRaises(PermissionError):
                    self.simulated(
                        pressure=self.fresh_pressure(),
                        budget=replace(self.budget, **change),
                    )

    def test_faults_deny_substituted_budget_even_with_matching_used_counters(self):
        forged = replace(
            self.budget,
            documents_remaining=self.budget.documents_remaining + 1,
        )
        with self.assertRaises(PermissionError):
            analyze_dispatch_faults(
                self.mandate, self.snapshot, forged,
                now=self.now, authorized=True,
            )

    def test_fault_ledger_denies_oversized_retained_event_window(self):
        snap = self.event_snapshot(("retry", "error"))
        with self.assertRaises(ValueError):
            analyze_dispatch_faults(
                self.mandate, snap, self.budget_for(snap),
                now=self.now, authorized=True, max_events=1,
            )

    def test_pending_dispatch_holds_uncertain_bytes(self):
        def pending(state):
            row = state["frontier"][0]
            state["usage"]["requests"] = 1
            state["usage"]["reserved_bytes"] = 4096
            state["sequence"] = 1
            state["pending_dispatch"] = {
                "url": row["url"], "item_url": row["url"],
                "original_url": row["original_url"],
                "limit": 4096, "sequence": 1,
                "started_at": self.f.now + 1,
            }
        snap = self.changed_snapshot(pending)
        budget = self.budget_for(snap)
        route = project_canonical_routes(
            self.mandate, snap, now=self.now, authorized=True,
        )
        ledger = analyze_dispatch_faults(
            self.mandate, snap, budget,
            now=self.now, authorized=True,
        )
        self.assertEqual(ledger.retained_uncertain_bytes, 4096)
        self.assertTrue(ledger.current_pending_dispatch)
        self.assertTrue(any(
            x.code == "retain_pending_bytes_until_authoritative_recovery"
            for x in ledger.recovery_queue
        ))
        self.assertEqual(
            self.simulated(snap, pressure=self.fresh_pressure(budget),
                           budget=budget, routes=route).steps,
            (),
        )

    def test_atlas_integrates_three_new_operational_stages(self):
        atlas = self.f.atlas()
        self.assertEqual(len(atlas.stages), 26)
        self.assertEqual(atlas.stages[-6].name, "canonical_route_graph_diagnostics")
        self.assertEqual(atlas.stages[-5].name, "resource_bounded_slice_simulation")
        self.assertEqual(atlas.stages[-4].name, "dispatch_fault_and_recovery_impacts")
        self.assertEqual(atlas.routes.run_id, atlas.run_id)
        self.assertEqual(atlas.simulation.routes_digest, atlas.routes.route_digest)
        self.assertEqual(atlas.faults.source_sequence, atlas.source_sequence)
        verify_dragon_atlas_trace(
            self.mandate, self.snapshot, atlas,
            now=self.now, authorized=True,
        )

    def test_full_atlas_uses_measured_telemetry_but_never_real_dispatch(self):
        observation = ResourceObservation(
            self.f.now + 1, 1<<30, 8<<30, 10**10, .1, 3, 0
        )
        atlas = compose_dragon_atlas(
            self.mandate, self.snapshot, objectives=(self.f.objective(),),
            source_policies=(), policy_snapshot_authenticated=True,
            now=self.now, authorized=True, telemetry=(observation,),
        )
        self.assertTrue(atlas.simulation.steps)
        self.assertFalse(atlas.simulation.actual_network_executed)
        self.assertFalse(atlas.dispatch_authorized)
        self.assertFalse(atlas.faults.mongo_commit_confirmed)
        verify_dragon_atlas_trace(
            self.mandate, self.snapshot, atlas,
            now=self.now, authorized=True,
        )

    def test_atlas_rejects_tampered_route_graph_stage(self):
        atlas = self.f.atlas()
        with self.assertRaises(ValueError):
            verify_dragon_atlas_trace(
                self.mandate, self.snapshot,
                replace(atlas, routes=replace(atlas.routes, route_digest="f"*64)),
                now=self.now, authorized=True,
            )

    def test_atlas_rejects_claimed_real_network_from_simulation(self):
        atlas = self.f.atlas()
        with self.assertRaises(PermissionError):
            verify_dragon_atlas_trace(
                self.mandate, self.snapshot,
                replace(atlas, simulation=replace(
                    atlas.simulation, actual_network_executed=True
                )),
                now=self.now, authorized=True,
            )

    def test_atlas_rejects_fabricated_mongo_commit(self):
        atlas = self.f.atlas()
        with self.assertRaises(PermissionError):
            verify_dragon_atlas_trace(
                self.mandate, self.snapshot,
                replace(atlas, faults=replace(
                    atlas.faults, mongo_commit_confirmed=True
                )),
                now=self.now, authorized=True,
            )


if __name__ == "__main__":
    unittest.main()
