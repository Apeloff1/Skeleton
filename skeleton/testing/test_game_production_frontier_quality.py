"""Real executable 20-gate frontier candidate and 6 upgrade regressions.

Fixtures are authored simulations, not actual native footage, model weights,
copyright certification or GPU performance observations.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.game.production_quality import QualityGateError, _digest
from skeleton.game.production_frontier_gates import (
    audit_asset_lineage, audit_longform_continuity, audit_route_coverage,
    audit_physics_consistency, audit_lod_fidelity, audit_localization,
    audit_comparative_performance, audit_frontier_candidate,
    verify_frontier_report,
)
from skeleton.game.production_frontier_assurance import (
    prioritized_quality_work, quality_report_delta,
    host_attest_report, verify_host_attestation,
    challenge_frontier_verifiers,
)
from skeleton.game.production_history import QualityHistoryStore
from skeleton.jeeves.game_production_quality_tools import frontier_quality_studio_handlers
from skeleton.jeeves.game_studio_tools import StudioCommand, studio_command_catalog
from skeleton.testing.test_game_production_deep_quality import candidate as base_candidate

_A, _B = "a" * 64, "b" * 64
_C = "c" * 64


def candidate():
    value = base_candidate()
    value["frontier"] = {
        "source_sha256": _A,
        "lineage": {
            "source_sha256": _A,
            "assets": [
                {"id": "original_mesh", "kind": "origin", "rights": "homebrew",
                 "source_sha256": _A, "sha256": _A, "inputs": []},
                {"id": "low_poly", "kind": "derived", "rights": "homebrew",
                 "source_sha256": _A, "sha256": _B, "inputs": ["original_mesh"]},
            ],
        },
        "timeline": {
            "source_sha256": _A,
            "cast": [{"id": "guide", "appearance_sha256": _A}],
            "scenes": [
                {"id": "departure", "act": 1, "tick": 0,
                 "actors": [{"id": "guide", "appearance_sha256": _A}],
                 "introduces": ["map_promise"]},
                {"id": "arrival", "act": 2, "tick": 5,
                 "actors": [{"id": "guide", "appearance_sha256": _A}],
                 "resolves": ["map_promise"]},
            ],
        },
        "routes": {
            "source_sha256": _A,
            "scenarios": [
                {"id": "wind", "minimum_distinct_paths": 1},
                {"id": "fog", "minimum_distinct_paths": 1},
            ],
            "observations": [
                {"scenario": "wind", "source_sha256": _A,
                 "edge_ids": ["bridge", "exit"], "won": True,
                 "independently_replayed": True},
                {"scenario": "fog", "source_sha256": _A,
                 "edge_ids": ["tunnel", "exit"], "won": True,
                 "independently_replayed": True},
            ],
        },
        "motion": {
            "source_sha256": _A, "max_acceleration": 5.0,
            "tolerance": 0.001, "frames": [
                {"actor": "hero", "time_s": 0, "position": [0, 0, 0],
                 "velocity": [1, 0, 0]},
                {"actor": "hero", "time_s": 1, "position": [1, 0, 0],
                 "velocity": [1, 0, 0]},
            ],
        },
        "lod": {
            "source_sha256": _A,
            "meshes": [
                {"mesh": "original_mesh", "level": 0, "triangles": 1000, "sha256": _A},
                {"mesh": "original_mesh", "level": 1, "triangles": 300, "sha256": _B},
            ],
            "observations": [
                {"mesh": "original_mesh", "frame": 0, "level": 0, "distance": 1},
                {"mesh": "original_mesh", "frame": 1, "level": 1, "distance": 10},
            ],
        },
        "localization": {
            "source_sha256": _A,
            "base": {"greeting": "Welcome {name}", "farewell": "Goodbye"},
            "languages": [
                {"id": "norwegian", "strings": {
                    "greeting": "Velkommen {name}", "farewell": "Farvel"}},
                {"id": "english", "strings": {
                    "greeting": "Welcome {name}", "farewell": "Goodbye"}},
            ],
        },
        "comparison": {
            "baseline": {
                "source_sha256": _B, "environment_sha256": _B,
                "workload_sha256": _C, "p50_ms": 14, "p95_ms": 20,
                "p99_ms": 30, "ram_mb": 512, "failure_count": 0,
                "unauthorized_effects": 0, "corrupted_saves": 0,
                "copyright_violations": 0,
            },
            "candidate": {
                "source_sha256": _A, "environment_sha256": _B,
                "workload_sha256": _C, "p50_ms": 12, "p95_ms": 19,
                "p99_ms": 28, "ram_mb": 500, "failure_count": 0,
                "unauthorized_effects": 0, "corrupted_saves": 0,
                "copyright_violations": 0,
            },
        },
    }
    return value


class FrontierGateTests(unittest.TestCase):
    def test_twenty_gates_pass_with_no_claim_of_release_authority(self):
        result = audit_frontier_candidate(candidate())
        self.assertEqual(20, len(result["gates"]))
        self.assertTrue(result["candidate_passed"])
        self.assertFalse(result["release_certified"])
        self.assertTrue(verify_frontier_report(candidate(), result)["independent_replay_passed"])

    def test_lineage_rejects_orphan_generated_asset(self):
        c = candidate()["frontier"]["lineage"]
        c["assets"][1]["inputs"] = []
        self.assertIn("orphan_derivative",
                      {f.code for f in audit_asset_lineage(c).findings})

    def test_lineage_deep_cycle_is_bounded(self):
        c = candidate()["frontier"]["lineage"]
        c["assets"][0]["inputs"] = ["low_poly"]
        self.assertIn("source_cycle", {f.code for f in audit_asset_lineage(c).findings})

    def test_all_frontier_contracts_pin_single_source_snapshot(self):
        for plane in ("lineage", "timeline", "routes", "motion", "lod", "localization"):
            c = candidate()
            c["frontier"][plane]["source_sha256"] = _B
            with self.subTest(plane=plane), self.assertRaises(QualityGateError):
                audit_frontier_candidate(c)
        c = candidate()
        c["frontier"]["comparison"]["candidate"]["source_sha256"] = _B
        with self.assertRaises(QualityGateError):
            audit_frontier_candidate(c)

    def test_lineage_rejects_foreign_source(self):
        c = candidate()["frontier"]["lineage"]
        c["assets"][0]["source_sha256"] = _B
        self.assertFalse(audit_asset_lineage(c).passed)

    def test_canon_rejects_appearance_change(self):
        c = candidate()["frontier"]["timeline"]
        c["scenes"][1]["actors"][0]["appearance_sha256"] = _B
        self.assertIn("appearance_drift",
                      {f.code for f in audit_longform_continuity(c).findings})

    def test_canon_rejects_unearned_payoff(self):
        c = candidate()["frontier"]["timeline"]
        c["scenes"][0]["introduces"].clear()
        self.assertIn("unearned_payoff",
                      {f.code for f in audit_longform_continuity(c).findings})

    def test_route_alternatives_must_be_distinct_and_verified(self):
        c = candidate()["frontier"]["routes"]
        c["scenarios"][0]["minimum_distinct_paths"] = 2
        self.assertFalse(audit_route_coverage(c).passed)
        c = candidate()["frontier"]["routes"]
        c["observations"][0]["independently_replayed"] = False
        self.assertIn("unverified_outcome",
                      {f.code for f in audit_route_coverage(c).findings})

    def test_physics_teleport_and_velocity_breach(self):
        c = candidate()["frontier"]["motion"]
        c["frames"][1]["position"] = [1000, 0, 0]
        self.assertIn("position_velocity_mismatch",
                      {f.code for f in audit_physics_consistency(c).findings})
        c = candidate()["frontier"]["motion"]
        c["frames"][1]["velocity"] = [100, 0, 0]
        self.assertIn("excess_acceleration",
                      {f.code for f in audit_physics_consistency(c).findings})

    def test_physics_nan_is_not_admitted(self):
        c = candidate()["frontier"]["motion"]
        c["frames"][1]["time_s"] = float("nan")
        with self.assertRaises(QualityGateError):
            audit_physics_consistency(c)

    def test_lod_triangle_inversion_and_flapping(self):
        c = candidate()["frontier"]["lod"]
        c["meshes"][1]["triangles"] = 2000
        self.assertIn("nondecreasing_triangles",
                      {f.code for f in audit_lod_fidelity(c).findings})
        c = candidate()["frontier"]["lod"]
        c["observations"][1]["distance"] = 1
        self.assertIn("lod_flapping", {f.code for f in audit_lod_fidelity(c).findings})

    def test_localization_detects_missing_variables(self):
        c = candidate()["frontier"]["localization"]
        c["languages"][0]["strings"]["greeting"] = "Hei"
        self.assertIn("placeholder_mismatch",
                      {f.code for f in audit_localization(c).findings})

    def test_comparison_rejects_change_of_workload(self):
        c = candidate()["frontier"]["comparison"]
        c["candidate"]["workload_sha256"] = _A
        self.assertIn("unfair_comparison",
                      {f.code for f in audit_comparative_performance(c).findings})

    def test_comparison_cannot_trade_safety_for_speed(self):
        c = candidate()["frontier"]["comparison"]
        c["candidate"]["corrupted_saves"] = 1
        self.assertFalse(audit_comparative_performance(c).passed)

    def test_independent_verifier_blocks_forged_summary(self):
        c = candidate()
        report = audit_frontier_candidate(c)
        report["gates"][0]["passed"] = False
        with self.assertRaises(QualityGateError):
            verify_frontier_report(c, report)


class FrontierUpgradesTests(unittest.TestCase):
    def test_dragon_mutates_seven_new_gates_and_summary(self):
        report = challenge_frontier_verifiers(candidate())
        self.assertEqual(7, report["verified_mutations"])
        self.assertTrue(report["forgery_rejected"])
        self.assertFalse(report["weights_updated"])

    def test_dragon_rejects_existing_faulted_baseline(self):
        c = candidate()
        c["frontier"]["routes"]["observations"].clear()
        with self.assertRaises(QualityGateError):
            challenge_frontier_verifiers(c)

    def test_host_hmac_integrity_requires_key_and_detects_tamper(self):
        c = audit_frontier_candidate(candidate())
        key = b"local-host-owner-created-secret-only-for-unit-tests!"
        proof = host_attest_report(c, host_secret=key,
                                  key_id="local-test-key", reviewer_id="reviewer-01")
        self.assertTrue(verify_host_attestation(c, proof, host_secret=key))
        forged = dict(proof)
        forged["hmac_sha256"] = _A
        self.assertFalse(verify_host_attestation(c, forged, host_secret=key))
        with self.assertRaises(QualityGateError):
            host_attest_report(c, host_secret=b"too-short",
                               key_id="local-test-key", reviewer_id="reviewer-01")

    def test_quality_delta_tracks_critical_regression(self):
        a = audit_frontier_candidate(candidate())
        c = candidate()
        c["frontier"]["lineage"]["assets"][0]["rights"] = "unknown"
        b = audit_frontier_candidate(c)
        delta = quality_report_delta(a, b)
        self.assertTrue(delta["critical_regression"])
        self.assertFalse(delta["strict_pareto_improvement"])
        self.assertIn("lineage", [x["gate"] for x in delta["regressed_gates"]])

    def test_quality_delta_is_objective_and_cannot_forge_pareto(self):
        a = candidate()
        a["frontier"]["timeline"]["scenes"][1]["resolves"].clear()
        failed = audit_frontier_candidate(a)
        passed = audit_frontier_candidate(candidate())
        delta = quality_report_delta(failed, passed)
        self.assertTrue(delta["strict_pareto_improvement"])
        self.assertFalse(delta["critical_regression"])

    def test_owner_queue_prioritizes_critical_source_and_never_automerge(self):
        c = candidate()
        c["frontier"]["lineage"]["assets"][1]["rights"] = "unknown"
        c["frontier"]["localization"]["languages"][0]["strings"].clear()
        plan = prioritized_quality_work(audit_frontier_candidate(c))
        self.assertEqual("P0", plan["tasks"][0]["priority"])
        self.assertEqual("asset_provenance_owner", plan["tasks"][0]["owner"])
        self.assertTrue(all(not x["auto_merge"] for x in plan["tasks"]))

    def test_persistent_twenty_gate_history_cas_restart_and_review(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.sqlite"
            report = audit_frontier_candidate(candidate())
            with QualityHistoryStore(path) as store:
                genesis = store.inspect("game-1")
                one = store.append("game-1", report, expected_generation=0,
                                   expected_head=genesis["head"])
                self.assertEqual(1, one["generation"])
                self.assertEqual(report, store.report_at("game-1", generation=1))
                before = store.inspect_reviews("game-1")
                review = store.review("game-1", reviewer_id="independent-operator",
                                      decision="accept_candidate", reason_sha256=_B,
                                      report_head_sha256=one["head"],
                                      expected_generation=0, expected_head=before["head"])
                self.assertFalse(review["production_approved"])
                with self.assertRaises(QualityGateError):
                    store.review("game-1", reviewer_id="independent-operator",
                                 decision="accept_candidate", reason_sha256=_B,
                                 report_head_sha256=one["head"],
                                 expected_generation=0, expected_head=before["head"])
            with QualityHistoryStore(path) as store:
                evidence = store.inspect("game-1", expected_head=one["head"])
                self.assertEqual(1, evidence["generation"])
                review_log = store.inspect_reviews("game-1")
                self.assertEqual(1, review_log["generation"])
                self.assertEqual(1, len(review_log["entries"]))

    def test_review_cannot_accept_failing_candidate(self):
        c = candidate()
        c["frontier"]["lineage"]["assets"][0]["rights"] = "unknown"
        with TemporaryDirectory() as directory:
            with QualityHistoryStore(Path(directory) / "evidence.sqlite") as store:
                one = store.append("game-1", audit_frontier_candidate(c),
                                   expected_generation=0, expected_head="0" * 64)
                with self.assertRaises(QualityGateError):
                    store.review("game-1", reviewer_id="reviewer-01",
                                 decision="accept_candidate", reason_sha256=_B,
                                 report_head_sha256=one["head"],
                                 expected_generation=0, expected_head="0" * 64)

    def test_review_tampering_blocks_replay(self):
        with TemporaryDirectory() as directory:
            with QualityHistoryStore(Path(directory) / "evidence.sqlite") as store:
                one = store.append("game-1", audit_frontier_candidate(candidate()),
                                   expected_generation=0, expected_head="0" * 64)
                store.review("game-1", reviewer_id="reviewer-01",
                             decision="request_changes", reason_sha256=_B,
                             report_head_sha256=one["head"],
                             expected_generation=0, expected_head="0" * 64)
                store.db.execute("UPDATE quality_operator_review SET receipt_sha256=?",
                                 (_A,))
                with self.assertRaises(QualityGateError):
                    store.inspect_reviews("game-1")

    def test_eight_studio_operations_with_host_source_and_operator(self):
        key = b"test-only-signer-created-and-kept-by-host-owner-123"
        with TemporaryDirectory() as directory:
            with QualityHistoryStore(Path(directory) / "evidence.sqlite") as store:
                handlers = frontier_quality_studio_handlers(
                    {"game-1": (_A, candidate)}, store=store,
                    reviewer_id="operator-01", integrity_key_id="host-key-01",
                    integrity_key=key,
                )
                catalog = studio_command_catalog()
                self.assertEqual(8, len(handlers))
                self.assertIn("game.quality.frontier.audit", catalog["read_operations"])
                self.assertIn("game.quality.frontier.review", catalog["write_operations"])
                def execute(op, data=None):
                    command = StudioCommand(op, "game-1", data or {})
                    return handlers[op](command, None)
                self.assertTrue(execute("game.quality.frontier.audit")["candidate_passed"])
                self.assertEqual(7, execute("game.quality.frontier.challenge")["verified_mutations"])
                self.assertTrue(verify_host_attestation(
                    execute("game.quality.frontier.audit"),
                    execute("game.quality.frontier.attest"), host_secret=key))
                one = execute("game.quality.frontier.record", {
                    "expected_generation": 0, "expected_head": "0" * 64})
                self.assertEqual(1, one["generation"])
                delta = execute("game.quality.frontier.diff", {"previous_generation": 1})
                self.assertFalse(delta["regressed_gates"])
                decision = execute("game.quality.frontier.review", {
                    "decision": "accept_candidate", "reason_sha256": _B,
                    "report_head_sha256": one["head"],
                    "expected_generation": 0, "expected_head": "0" * 64})
                self.assertEqual("operator-01", decision["reviewer_id"])
                self.assertEqual(1, execute("game.quality.frontier.reviews.inspect")["generation"])
                self.assertEqual(0, execute("game.quality.frontier.work")["tasks"].__len__())
                with self.assertRaises(QualityGateError):
                    command = StudioCommand("game.quality.frontier.audit", "foreign", {})
                    handlers[command.operation](command, None)


if __name__ == "__main__":
    unittest.main()
