"""34-gate candidate studio: source, adversarial, routing and persistence regressions.

Fixtures are deliberately synthetic; positive results NEVER attest native devices,
real gameplay network sessions, physical audio captures or 24h wall-clock runs.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.game.production_quality import QualityGateError
from skeleton.game.production_advanced_gates import (
    NAMES, audit_advanced_studio, verify_advanced_studio,
)
from skeleton.game.production_advanced_assurance import (
    verify_advanced_report_structure, challenge_advanced_studio,
    compare_advanced_studio_reports, advanced_studio_impact_graph,
    advanced_studio_work_queue,
)
from skeleton.game.production_history import QualityHistoryStore
from skeleton.jeeves.game_advanced_studio_quality_tools import advanced_studio_quality_handlers
from skeleton.jeeves.game_studio_tools import StudioCommand, studio_command_catalog
from skeleton.testing.test_game_production_studio_quality import candidate as studio_candidate

SHA = "a" * 64
ALT = "b" * 64
THIRD = "c" * 64
GENESIS = "0" * 64


def candidate():
    """Full 34-plane, source-pinned synthetic candidate."""
    c = studio_candidate()
    c["studio"]["advanced"] = {
        "source_sha256": SHA,
        "audio": {
            "source_sha256": SHA,
            "buses": [{"id": "music", "gain_db": 0, "limiter": True}],
            "cues": [
                {"id": "arrival", "asset_sha256": SHA, "bus": "music",
                 "transitions": ["storm"]},
                {"id": "storm", "asset_sha256": ALT, "bus": "music",
                 "transitions": ["arrival"]},
            ],
            "observations": [
                {"cue": cue, "source_sha256": SHA, "capture_sha256": ALT,
                 "true_peak_dbfs": -4, "integrated_lufs": -18, "measured": True}
                for cue in ("arrival", "storm")
            ],
        },
        "procedural": {
            "source_sha256": SHA,
            "generators": [{
                "id": "islands", "algorithm_sha256": SHA,
                "seeds": [
                    {"seed": seed, "first_sha256": digest, "replay_sha256": digest,
                     "replay_engine_sha256": ALT, "source_sha256": SHA,
                     "independent": True}
                    for seed, digest in ((123, SHA), (456, ALT))
                ],
            }],
        },
        "economy": {
            "source_sha256": SHA,
            "currencies": ["coin"],
            "transactions": [{
                "id": "transfer", "entries": [
                    {"account": "player", "currency": "coin", "amount": -20},
                    {"account": "merchant", "currency": "coin", "amount": 20},
                ], "replayed": True,
            }],
            "recipes": [{
                "id": "planks", "ingredients": [{"item": "wood", "quantity": 2}],
                "output": "plank", "output_quantity": 1, "requires_recipes": [],
            }],
        },
        "multiplayer": {
            "source_sha256": SHA, "peers": ["host", "client"], "max_divergence_ms": 60,
            "frames": [
                {"peer": peer, "tick": tick, "source_sha256": SHA,
                 "state_sha256": (SHA if tick == 1 else ALT if tick == 2 else THIRD),
                 "input_sha256": ALT, "replay_sha256": SHA,
                 "replayed": True, "lag_ms": 8}
                for peer in ("host", "client") for tick in (1, 2, 3)
            ],
        },
        "transport": {
            "source_sha256": SHA,
            "nodes": ["port", "airfield", "sky_island"],
            "origin": "port", "destinations": ["sky_island"],
            "links": [
                {"id": "walk", "from": "port", "to": "airfield",
                 "mode": "foot", "duration_s": 20, "hazardous": False,
                 "bidirectional": True},
                {"id": "flight", "from": "airfield", "to": "sky_island",
                 "mode": "air", "duration_s": 50, "hazardous": False,
                 "bidirectional": True},
            ],
        },
        "privacy": {
            "source_sha256": SHA,
            "purposes": [{
                "id": "analytics", "retention_hours": 24,
                "opt_in_default": False, "personal_data": False,
            }],
            "observations": [
                {"purpose": "analytics", "source_sha256": SHA,
                 "event_schema_sha256": ALT, "consent": consent,
                 "emitted": consent, "contains_raw_identifier": False,
                 "independently_replayed": True}
                for consent in (True, False)
            ],
        },
        "endurance": {
            "source_sha256": SHA, "max_memory_mb": 512,
            "max_p99_frame_ms": 33.4, "max_recovery_ms": 3000,
            "samples": [
                {"elapsed_s": time, "resident_mb": 128 + j * 5,
                 "p99_frame_ms": 16, "source_sha256": SHA,
                 "telemetry_sha256": ALT, "observed": True}
                for j, time in enumerate((0, 43200, 90000))
            ],
            "restores": [{
                "before_sha256": SHA, "after_sha256": SHA,
                "capture_sha256": ALT, "recovery_ms": 45,
                "source_sha256": SHA, "replayed": True,
            }],
        },
    }
    return c


MUTATIONS = (
    ("audio_mix", lambda c: c["studio"]["advanced"]["audio"]["observations"][0].update(true_peak_dbfs=8)),
    ("procedural_replay", lambda c: c["studio"]["advanced"]["procedural"]["generators"][0]["seeds"][0].update(replay_sha256=THIRD)),
    ("economy_integrity", lambda c: c["studio"]["advanced"]["economy"]["transactions"][0]["entries"][0].update(amount=-19)),
    ("multiplayer_sync", lambda c: c["studio"]["advanced"]["multiplayer"]["frames"][0].update(state_sha256=THIRD)),
    ("transport_paths", lambda c: c["studio"]["advanced"]["transport"]["links"][0].update(to="missing")),
    ("privacy_consent", lambda c: c["studio"]["advanced"]["privacy"]["observations"][1].update(emitted=True)),
    ("endurance_recovery", lambda c: c["studio"]["advanced"]["endurance"]["restores"][0].update(after_sha256=ALT)),
)


class AdvancedGameStudioTests(unittest.TestCase):
    def test_34_domain_candidate_is_source_bound_non_certifying(self):
        c = candidate()
        result = audit_advanced_studio(c)
        self.assertEqual(34, len(result["gates"]))
        self.assertEqual(NAMES, tuple(g["name"] for g in result["gates"][-7:]))
        self.assertTrue(result["candidate_passed"])
        self.assertFalse(result["release_certified"])
        self.assertEqual(34, verify_advanced_studio(c, result)["gate_count"])
        self.assertEqual(34, verify_advanced_report_structure(result)["gate_count"])

    def test_seven_evidence_mutations_fail_exact_owner(self):
        for gate, mutate in MUTATIONS:
            with self.subTest(gate=gate):
                c = candidate()
                mutate(c)
                report = audit_advanced_studio(c)
                self.assertFalse(next(x for x in report["gates"]
                                      if x["name"] == gate)["passed"])
                self.assertFalse(report["candidate_passed"])

    def test_all_new_source_subcontracts_require_exact_digest(self):
        for key in ("audio", "procedural", "economy", "multiplayer",
                    "transport", "privacy", "endurance"):
            with self.subTest(key=key):
                c = candidate()
                c["studio"]["advanced"][key]["source_sha256"] = THIRD
                with self.assertRaises(QualityGateError):
                    audit_advanced_studio(c)

    def test_missing_plane_and_nonfinite_evidence_refused(self):
        c = candidate()
        del c["studio"]["advanced"]["audio"]
        with self.assertRaises(QualityGateError):
            audit_advanced_studio(c)
        c = candidate()
        c["studio"]["advanced"]["audio"]["buses"][0]["gain_db"] = float("nan")
        with self.assertRaises(QualityGateError):
            audit_advanced_studio(c)

    def test_audio_transition_and_observation_coverage(self):
        c = candidate()
        c["studio"]["advanced"]["audio"]["cues"][0]["transitions"] = ["unknown"]
        c["studio"]["advanced"]["audio"]["observations"].pop()
        findings = [f["code"] for f in audit_advanced_studio(c)["findings"]
                    if f["gate"] == "audio_mix"]
        self.assertIn("unknown_transition", findings)
        self.assertIn("missing_mix_observation", findings)

    def test_procedural_variation_collapse_rejected(self):
        c = candidate()
        p = c["studio"]["advanced"]["procedural"]["generators"][0]["seeds"]
        p[1]["first_sha256"] = SHA
        p[1]["replay_sha256"] = SHA
        self.assertIn("collapsed_variation",
                      [f["code"] for f in audit_advanced_studio(c)["findings"]])

    def test_economy_recipe_cycle_refused(self):
        c = candidate()
        c["studio"]["advanced"]["economy"]["recipes"][0]["requires_recipes"] = ["planks"]
        self.assertIn("craft_dependency_cycle",
                      [f["code"] for f in audit_advanced_studio(c)["findings"]])

    def test_network_missing_ack_and_unbounded_lag(self):
        c = candidate()
        m = c["studio"]["advanced"]["multiplayer"]
        m["frames"].pop()
        m["frames"][0]["lag_ms"] = 500
        codes = [x["code"] for x in audit_advanced_studio(c)["findings"]
                 if x["gate"] == "multiplayer_sync"]
        self.assertIn("missing_tick_ack", codes)
        self.assertIn("lag_budget_exceeded", codes)

    def test_transport_hazard_without_fallback_and_route_break(self):
        c = candidate()
        t = c["studio"]["advanced"]["transport"]
        t["links"][1]["hazardous"] = True
        t["links"][1]["mitigated"] = False
        t["links"][1]["fallback"] = False
        t["links"].pop(0)
        codes = [x["code"] for x in audit_advanced_studio(c)["findings"]
                 if x["gate"] == "transport_paths"]
        self.assertIn("hazard_no_fallback", codes)
        self.assertIn("unreachable_destination", codes)

    def test_hazard_declared_fallback_requires_real_nonhazardous_route(self):
        c = candidate()
        flight = c["studio"]["advanced"]["transport"]["links"][1]
        flight.update(hazardous=True, mitigated=True, fallback=True)
        codes = [x["code"] for x in audit_advanced_studio(c)["findings"]
                 if x["gate"] == "transport_paths"]
        self.assertIn("no_independent_fallback", codes)

    def test_opt_out_replay_required_even_when_opt_in_works(self):
        c = candidate()
        c["studio"]["advanced"]["privacy"]["observations"].pop()
        self.assertIn("missing_opt_out_probe",
                      [x["code"] for x in audit_advanced_studio(c)["findings"]])

    def test_long_session_24h_coverage_and_recovery_state(self):
        c = candidate()
        e = c["studio"]["advanced"]["endurance"]
        e["samples"][-1]["elapsed_s"] = 70000
        e["restores"][0]["after_sha256"] = ALT
        codes = [x["code"] for x in audit_advanced_studio(c)["findings"]
                 if x["gate"] == "endurance_recovery"]
        self.assertIn("insufficient_24h_coverage", codes)
        self.assertIn("failed_stateful_restore", codes)

    def test_independent_reviewer_rejects_rewritten_report(self):
        c = candidate()
        report = audit_advanced_studio(c)
        report["gates"][-1]["passed"] = False
        with self.assertRaises(QualityGateError):
            verify_advanced_studio(c, report)
        with self.assertRaises(QualityGateError):
            verify_advanced_report_structure(report)

    def test_dragon_challenges_all_seven_and_both_forgery_paths(self):
        result = challenge_advanced_studio(candidate())
        self.assertEqual(7, result["attacks_rejected"])
        self.assertTrue(result["independent_forgery_rejected"])
        self.assertTrue(result["summary_forgery_rejected"])
        self.assertFalse(result["production_certified"])

    def test_dragon_refuses_dirty_baseline(self):
        c = candidate()
        MUTATIONS[0][1](c)
        with self.assertRaises(QualityGateError):
            challenge_advanced_studio(c)

    def test_objective_regression_and_repair_queue(self):
        c = candidate()
        base = audit_advanced_studio(c)
        MUTATIONS[5][1](c)
        changed = audit_advanced_studio(c)
        result = compare_advanced_studio_reports(base, changed)
        self.assertTrue(result["critical_regression"])
        self.assertFalse(result["strict_pareto_improvement"])
        queue = advanced_studio_work_queue(changed)
        self.assertEqual("privacy_telemetry_owner", queue["items"][0]["owner"])
        self.assertEqual("P0", queue["items"][0]["priority"])
        self.assertFalse(queue["auto_mutation_executed"])
        improvement = compare_advanced_studio_reports(changed, base)
        self.assertTrue(improvement["strict_pareto_improvement"])

    def test_impact_graph_exposes_upstream_without_mutations(self):
        c = candidate()
        MUTATIONS[4][1](c)
        graph = advanced_studio_impact_graph(audit_advanced_studio(c))
        self.assertIn("routes", graph["upstream_contracts_to_revalidate"])
        self.assertFalse(graph["mutation_authorized"])

    def test_34_gate_sqlite_cas_and_reopened_history(self):
        with TemporaryDirectory() as root:
            p = Path(root) / "quality.db"
            clean = audit_advanced_studio(candidate())
            with QualityHistoryStore(p) as store:
                receipt = store.append("sky-island", clean,
                                       expected_generation=0, expected_head=GENESIS)
                self.assertEqual(1, receipt["generation"])
                self.assertEqual(clean, store.report_at("sky-island", generation=1))
                with self.assertRaises(QualityGateError):
                    store.append("sky-island", clean,
                                 expected_generation=0, expected_head=GENESIS)
            with QualityHistoryStore(p) as reopened:
                self.assertEqual(1, reopened.inspect("sky-island")["generation"])

    def test_jeeves_handlers_are_host_scoped_and_registered(self):
        c = candidate()
        with TemporaryDirectory() as root:
            with QualityHistoryStore(Path(root) / "studio.db") as store:
                handlers = advanced_studio_quality_handlers(
                    {"game-a": (SHA, lambda: c)}, store=store,
                    operator_id="operator-a")
                self.assertEqual(8, len(handlers))
                catalog = studio_command_catalog()
                self.assertIn("game.studio.advanced.audit", catalog["read_operations"])
                self.assertIn("game.studio.advanced.record", catalog["write_operations"])
                audit = StudioCommand("game.studio.advanced.audit", "game-a", {})
                self.assertEqual(34, len(handlers[audit.operation](audit, None)["gates"]))
                dragon = StudioCommand("game.studio.advanced.dragon", "game-a", {})
                self.assertEqual(7, handlers[dragon.operation](dragon, None)["attacks_rejected"])
                inspect = StudioCommand("game.studio.advanced.impact", "game-a", {})
                self.assertFalse(handlers[inspect.operation](inspect, None)["mutation_authorized"])
                record = StudioCommand("game.studio.advanced.record", "game-a", {
                    "expected_generation": 0, "expected_head": GENESIS})
                self.assertEqual(1, handlers[record.operation](record, None)["generation"])
                compare = StudioCommand("game.studio.advanced.diff", "game-a", {
                    "prior_generation": 1})
                self.assertFalse(handlers[compare.operation](compare, None)["source_changed"])
                forged = StudioCommand("game.studio.advanced.audit", "game-b", {})
                with self.assertRaises(QualityGateError):
                    handlers[audit.operation](forged, None)
                wrong = StudioCommand("game.studio.advanced.audit", "game-a", {"source": "fake"})
                with self.assertRaises(QualityGateError):
                    handlers[audit.operation](wrong, None)


if __name__ == "__main__":
    unittest.main()
