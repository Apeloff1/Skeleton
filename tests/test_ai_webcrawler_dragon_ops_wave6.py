"""Six-gate Dragon operational replay, custody and denial regressions.

Every fixture is a real canonical CrawlRun snapshot. These tests perform no
network I/O, database writes, worker spawning, source promotion or model calls.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256
import json
import unittest

import test_ai_webcrawler_dragon_atlas as fixtures
from skeleton.ai.webcrawler.operations import CrawlRun
from skeleton.ai.webcrawler.dragon_campaign_stack import (
    compose_operational_assurance, verify_operational_assurance,
    inspect_operational_timeline, govern_canonical_origins,
    assess_restart_handshake, recommend_ops_capacity,
    prepare_dispatch_envelope, compile_operator_runbook,
    RecoveryWitness, ResourceObservation, project_budget,
    project_canonical_routes,
)


class DragonOperationalWave6Tests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid",
        )
        self.f.setUp()
        self.now = self.f.now + 3
        self.snapshot = self.f.empty
        self.mandate = self.f.mandate

    def observation(self, **changes):
        fields = {
            "at": self.now - 1, "memory_available_bytes": 2**30,
            "memory_total_bytes": 8 * 2**30,
            "disk_free_bytes": 10**10, "cpu_pressure": .1,
            "worker_count": 3, "active_fetches": 0,
        }
        fields.update(changes)
        return ResourceObservation(**fields)

    def witness(self, snapshot=None, **changes):
        row = self.snapshot if snapshot is None else snapshot
        fields = {
            "source_snapshot_digest": row["snapshot_digest"],
            "expected_run_sequence": row["sequence"],
            "expected_worker_epoch": 7,
            "physical_worker_join_observed": True,
            "old_lease_revoked": True,
            "durable_mongo_checkpoint_confirmed": True,
            "owner_scope_reauthenticated": True,
            "live_consent_reauthenticated": True,
        }
        fields.update(changes)
        return RecoveryWitness(**fields)

    def report(self, snapshot=None, *, observations=(), witness=None):
        row = self.snapshot if snapshot is None else snapshot
        return compose_operational_assurance(
            self.mandate, row, now=self.now, authorized=True,
            resource_observations=observations,
            recovery_witness=witness,
        )

    def with_events(self, kinds):
        run = CrawlRun.from_snapshot(self.snapshot)
        for index, kind in enumerate(kinds):
            run._event(
                kind, now=self.now + index * .01,
                url="https://example.com/archive",
                reason="synthetic bounded source test",
            )
        return run.snapshot()

    def test_default_exact_six_stage_chain(self):
        result = self.report()
        self.assertEqual(len(result.stages), 6)
        self.assertEqual([x.ordinal for x in result.stages], list(range(6)))
        self.assertEqual(result.stages[0].name, "exact_canonical_event_timeline")
        self.assertEqual(result.stages[-1].name, "review_only_operator_recovery_runbook")
        self.assertEqual(result.stages[0].previous_chain_digest, "0" * 64)
        self.assertEqual(result.stages[1].previous_chain_digest,
                         result.stages[0].chain_digest)
        self.assertEqual(result.run_sequence, self.snapshot["sequence"])
        self.assertEqual(result.source_snapshot_digest,
                         self.snapshot["snapshot_digest"])

    def test_missing_measured_samples_default_to_zero_capacity(self):
        result = self.report()
        self.assertEqual(result.capacity.samples_observed, 0)
        self.assertEqual(result.capacity.suggested_slice_steps, 0)
        self.assertEqual(result.dispatch.steps, ())
        self.assertEqual(result.dispatch.feasible_hypothetical_requests, 0)
        self.assertIn("no_measured_resource_telemetry", result.capacity.holds)

    def test_missing_worker_confirmation_is_not_assumed(self):
        result = self.report()
        self.assertFalse(result.recovery.witness_present)
        self.assertFalse(result.recovery.real_worker_fenced)
        self.assertFalse(result.recovery.authoritative_checkpoint_committed)
        self.assertFalse(result.recovery.runtime_dispatch_authorized)
        self.assertIn("no_canonical_worker_and_mongo_witness",
                      result.recovery.held_reasons)

    def test_default_host_governor_keeps_robots_unknown(self):
        result = self.report()
        self.assertEqual(result.hosts.cold_robots_origins, 2)
        self.assertEqual(result.hosts.stale_robots_origins, 0)
        self.assertEqual(result.hosts.ready_frontier_items, 2)
        self.assertTrue(all(x.robot_rules_need_fresh_confirmation
                            for x in result.hosts.origins))
        self.assertTrue(all(not x.live_robots_permission_granted
                            for x in result.hosts.origins))

    def test_all_emitted_data_is_source_text_free(self):
        sentinel = "THIS_IS_AN_UNTRUSTED_SOURCE_BODY_ONLY_56789"
        snap = self.f.with_sources((
            "https://example.com/a", fixtures.research_text(sentinel),
        ))
        result = self.report(snap)
        body = json.dumps(asdict(result))
        self.assertNotIn(sentinel, body)
        self.assertNotIn("https://example.com/archive", body)
        self.assertFalse(result.source_text_exported)
        self.assertFalse(result.credential_exported)

    def test_no_real_network_lease_or_training_from_read_only_report(self):
        result = self.report()
        self.assertTrue(result.read_only)
        self.assertFalse(result.mongo_state_mutated)
        self.assertFalse(result.physical_worker_started)
        self.assertFalse(result.worker_lease_authenticated)
        self.assertFalse(result.network_request_performed)
        self.assertFalse(result.publication_or_training_granted)
        self.assertFalse(result.dispatch.execution_capability_issued)

    def test_repeated_composition_is_deterministic(self):
        self.assertEqual(self.report(), self.report())

    def test_current_report_exact_replay_verified(self):
        result = self.report()
        verify_operational_assurance(
            self.mandate, self.snapshot, result,
            now=self.now, authorized=True,
        )

    def test_report_replay_fails_if_clock_changes(self):
        report = self.report()
        with self.assertRaises(PermissionError):
            verify_operational_assurance(
                self.mandate, self.snapshot, report,
                now=self.now + 1, authorized=True,
            )

    def test_report_replay_rejects_missing_source_receipt_stage(self):
        result = self.report()
        forgery = replace(result, stages=result.stages[:-1])
        with self.assertRaises(PermissionError):
            verify_operational_assurance(
                self.mandate, self.snapshot, forgery,
                now=self.now, authorized=True,
            )

    def test_report_replay_rejects_stage_swaps(self):
        result = self.report()
        swapped = (result.stages[1], result.stages[0], *result.stages[2:])
        with self.assertRaises(PermissionError):
            verify_operational_assurance(
                self.mandate, self.snapshot,
                replace(result, stages=swapped),
                now=self.now, authorized=True,
            )

    def test_report_replay_rejects_forged_network_permission(self):
        result = self.report()
        with self.assertRaises(PermissionError):
            verify_operational_assurance(
                self.mandate, self.snapshot,
                replace(result, network_request_performed=True),
                now=self.now, authorized=True,
            )

    def test_report_replay_rejects_modified_capacity(self):
        result = self.report()
        with self.assertRaises(PermissionError):
            verify_operational_assurance(
                self.mandate, self.snapshot,
                replace(result, capacity=replace(
                    result.capacity, suggested_slice_steps=9,
                )),
                now=self.now, authorized=True,
            )

    def test_report_replay_rejects_forged_worker_witness(self):
        result = self.report()
        with self.assertRaises(PermissionError):
            verify_operational_assurance(
                self.mandate, self.snapshot, result,
                now=self.now, authorized=True,
                recovery_witness=self.witness(),
            )

    def test_unsigned_caller_witness_never_claims_backend_proof(self):
        report = self.report(
            observations=(self.observation(),), witness=self.witness(),
        )
        self.assertTrue(report.recovery.operator_asserted_ready)
        self.assertTrue(report.recovery.witness_present)
        self.assertFalse(report.recovery.real_worker_fenced)
        self.assertFalse(report.recovery.authoritative_checkpoint_committed)
        self.assertFalse(report.dispatch.physical_worker_lease_granted)
        self.assertFalse(report.dispatch.execution_capability_issued)

    def test_recovery_witness_rejects_stale_snapshot(self):
        with self.assertRaises(RuntimeError):
            self.report(witness=self.witness(
                source_snapshot_digest="a" * 64
                if self.snapshot["snapshot_digest"] != "a" * 64 else "b" * 64,
            ))

    def test_recovery_witness_rejects_stale_sequence(self):
        with self.assertRaises(RuntimeError):
            self.report(witness=self.witness(
                expected_run_sequence=self.snapshot["sequence"] + 1,
            ))

    def test_recovery_witness_cannot_claim_backend_authority(self):
        with self.assertRaises(ValueError):
            self.witness(source_authority="verified_backend_signed")

    def test_recovery_witness_requires_exact_boolean_types(self):
        with self.assertRaises(TypeError):
            self.witness(physical_worker_join_observed=1)

    def test_incomplete_worker_witness_blocks_simulated_work(self):
        report = self.report(
            observations=(self.observation(),),
            witness=self.witness(old_lease_revoked=False),
        )
        self.assertIn("operator_recovery_witness_incomplete",
                      report.recovery.held_reasons)
        self.assertEqual(report.dispatch.feasible_hypothetical_requests, 0)

    def test_measured_resources_without_worker_witness_remain_held(self):
        report = self.report(observations=(self.observation(),))
        self.assertEqual(report.capacity.samples_observed, 1)
        self.assertEqual(report.capacity.suggested_slice_steps, 0)
        self.assertIn("no_canonical_worker_and_mongo_witness",
                      report.capacity.holds)

    def test_explicit_worker_witness_and_telemetry_can_propose_robots_only(self):
        report = self.report(
            observations=(self.observation(),),
            witness=self.witness(),
        )
        self.assertGreater(report.dispatch.feasible_hypothetical_requests, 0)
        self.assertLessEqual(report.dispatch.feasible_hypothetical_requests, 4)
        self.assertTrue(all(x.action == "robots_preflight_only"
                            for x in report.dispatch.steps))
        self.assertTrue(all(x.requires_live_robots_check
                            for x in report.dispatch.steps))
        self.assertTrue(all(x.opaque_url_digest and len(x.opaque_url_digest) == 64
                            for x in report.dispatch.steps))
        self.assertFalse(report.dispatch.execution_capability_issued)
        self.assertIn("requires_fresh_backend_admission_before_any_network",
                      report.dispatch.blocked_reasons)
        self.assertTrue(all(x.actual_request_performed is False
                            for x in report.dispatch.steps))

    def test_valid_measured_runtime_sample_is_replayable(self):
        observations = (self.observation(),)
        witness = self.witness()
        report = self.report(observations=observations, witness=witness)
        verify_operational_assurance(
            self.mandate, self.snapshot, report,
            now=self.now, authorized=True,
            recovery_witness=witness, resource_observations=observations,
        )

    def test_stale_resource_telemetry_blocks_parallel_slices(self):
        report = self.report(
            observations=(self.observation(at=self.now-180),),
            witness=self.witness(),
        )
        self.assertEqual(report.capacity.suggested_slice_steps, 0)
        self.assertIn("resource_telemetry_stale", report.capacity.holds)
        self.assertEqual(report.dispatch.feasible_hypothetical_requests, 0)

    def test_memory_shortage_blocks_parallel_slices(self):
        report = self.report(
            observations=(self.observation(
                memory_available_bytes=1024,
            ),), witness=self.witness(),
        )
        self.assertEqual(report.capacity.suggested_parallel_workers, 0)
        self.assertIn("memory_headroom_low", report.capacity.holds)

    def test_disk_shortage_blocks_parallel_slices(self):
        report = self.report(
            observations=(self.observation(disk_free_bytes=4096),),
            witness=self.witness(),
        )
        self.assertEqual(report.dispatch.feasible_hypothetical_requests, 0)
        self.assertIn("disk_headroom_low", report.capacity.holds)

    def test_high_cpu_pressure_blocks_parallel_slices(self):
        report = self.report(
            observations=(self.observation(cpu_pressure=.97),),
            witness=self.witness(),
        )
        self.assertEqual(report.dispatch.feasible_hypothetical_requests, 0)
        self.assertIn("cpu_pressure_critical", report.capacity.holds)

    def test_future_resource_observation_is_rejected(self):
        with self.assertRaises(ValueError):
            self.report(
                observations=(self.observation(at=self.now + 12),),
                witness=self.witness(),
            )

    def test_resource_sample_window_is_bounded(self):
        with self.assertRaises(ValueError):
            self.report(observations=tuple(self.observation()
                                           for _ in range(33)))

    def test_origin_governor_reports_fail_closed_future_clock(self):
        snapshot = self.with_events(("retry",))
        report = self.report(snapshot)
        self.assertEqual(report.timeline.events[-1].kind, "retry")
        self.assertEqual(report.hosts.origins[0].retry_or_transport_faults, 1)

    def test_event_history_reports_ring_truncation(self):
        snapshot = self.with_events(("retry",) * 70)
        report = self.report(snapshot)
        self.assertEqual(len(report.timeline.events), 64)
        self.assertTrue(report.timeline.retained_history_incomplete)
        self.assertIn("earlier_crawl_events_not_retained",
                      report.timeline.review_holds)

    def test_event_timestamp_anomaly_triggers_review_hold(self):
        snapshot = self.with_events(("error",))
        run = CrawlRun.from_snapshot(snapshot)
        run._event("retry", now=self.now + 700,
                   url="https://example.com/archive",
                   reason="synthetic future clock")
        report = self.report(run.snapshot())
        self.assertTrue(report.timeline.future_clock_receipts)
        self.assertIn("future_event_clock_receipt",
                      report.timeline.review_holds)
        self.assertEqual(report.capacity.suggested_slice_steps, 0)

    def test_replay_rejects_changed_canonical_snapshot(self):
        report = self.report()
        altered = self.with_events(("retry",))
        with self.assertRaises(PermissionError):
            verify_operational_assurance(
                self.mandate, altered, report, now=self.now, authorized=True,
            )

    def test_replay_rejects_revoked_operator_authority(self):
        with self.assertRaises(PermissionError):
            compose_operational_assurance(
                self.mandate, self.snapshot, now=self.now,
                authorized=False,
            )

    def test_replay_rejects_expired_consent(self):
        with self.assertRaises(PermissionError):
            compose_operational_assurance(
                self.mandate, self.snapshot,
                now=self.mandate.scope.expires_at,
                authorized=True,
            )

    def test_replay_rejects_foreign_snapshot_scope(self):
        altered = dict(self.snapshot)
        altered["binding"] = dict(self.snapshot["binding"])
        altered["binding"]["scope"] = {
            "tenant_id": "attacker", "owner_id": "attacker",
        }
        with self.assertRaises(PermissionError):
            self.report(altered)

    def test_recovery_and_operator_runbook_are_never_auto_executed(self):
        report = self.report()
        self.assertGreater(report.runbook.critical_step_count, 0)
        self.assertTrue(report.runbook.requires_human_review)
        self.assertFalse(report.runbook.actual_worker_intervention_performed)
        self.assertFalse(report.runbook.merge_or_release_approved)
        self.assertTrue(all(x.requires_backend_authority
                            and not x.automatically_executed
                            and not x.completed_or_approved
                            for x in report.runbook.steps))

    def test_runbook_rejects_foreign_capacity_receipt(self):
        report = self.report()
        altered = replace(report.capacity,
                          recovery_digest="f" * 64)
        with self.assertRaises(PermissionError):
            compile_operator_runbook(
                self.mandate, report.timeline, report.hosts,
                report.recovery, altered, report.dispatch,
            )

    def test_source_budget_forgery_is_not_accepted(self):
        report = self.report()
        from skeleton.ai.webcrawler.dragon_campaign_stack.integration import inspect_crawl_campaign
        budget = inspect_crawl_campaign(
            self.snapshot, self.mandate, now=self.now,
            authorized=True,
        ).budget
        with self.assertRaises(PermissionError):
            compose_operational_assurance(
                self.mandate, self.snapshot, now=self.now,
                authorized=True,
                budget=replace(budget,
                               bytes_remaining=budget.bytes_remaining+1),
            )

    def test_explicit_budget_matching_current_canonical_usage_is_accepted(self):
        from skeleton.ai.webcrawler.dragon_campaign_stack.integration import inspect_crawl_campaign
        budget = inspect_crawl_campaign(
            self.snapshot, self.mandate, now=self.now,
            authorized=True,
        ).budget
        report = compose_operational_assurance(
            self.mandate, self.snapshot, now=self.now,
            authorized=True, budget=budget,
        )
        self.assertEqual(report.run_sequence, self.snapshot["sequence"])

    def test_plan_fingerprint_never_contains_requested_url(self):
        report = self.report(
            observations=(self.observation(),),
            witness=self.witness(),
        )
        for proposed in report.dispatch.steps:
            self.assertNotIn("https://", repr(proposed))
            self.assertNotIn("/archive", repr(proposed))
            self.assertEqual(proposed.worst_case_request_bytes,
                             min(65536, self.mandate.request.max_response_bytes))

    def test_envelope_rejects_cross_crawl_governor_receipt(self):
        report = self.report()
        from skeleton.ai.webcrawler.dragon_campaign_stack.integration import inspect_crawl_campaign
        budget = inspect_crawl_campaign(
            self.snapshot, self.mandate, now=self.now,
            authorized=True,
        ).budget
        routes = project_canonical_routes(
            self.mandate, self.snapshot, now=self.now, authorized=True,
        )
        with self.assertRaises(PermissionError):
            prepare_dispatch_envelope(
                self.mandate, self.snapshot, budget, routes,
                replace(report.hosts, source_snapshot_digest="f"*64),
                report.recovery, report.capacity, now=self.now, authorized=True,
            )

    def test_operator_runbook_has_stable_priority_sort(self):
        result = self.report()
        codes = [x.code for x in result.runbook.steps]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(0 <= x.ordinal < len(codes)
                            for x in result.runbook.steps))
        self.assertIn("complete_durable_restart_fence", codes)
        self.assertIn("collect_authenticated_live_resource_samples", codes)


if __name__ == "__main__":
    unittest.main()
