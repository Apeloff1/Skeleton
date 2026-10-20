"""Twenty-seven game production gate and six integration-upgrade acceptance cases.

Entire fixture consists of source-bound synthetic observations. Tests must never
claim actual native engine runs, real device latency, trained weights or legal
rights clearance from these self-authored values.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.game.production_quality import QualityGateError
from skeleton.game.production_studio_gates import (
    audit_cinematic_direction, audit_dialogue_sync, audit_npc_behavior,
    audit_world_streaming, audit_save_evolution, audit_dynamic_world,
    audit_controller_latency, audit_complete_studio, verify_complete_studio,
)
from skeleton.game.production_studio_assurance import (
    verify_report_structure, challenge_studio_verifiers,
    compare_studio_reports, studio_repair_queue, inspect_native_game_witness,
)
from skeleton.game.production_history import QualityHistoryStore
from skeleton.game.production_studio_repair import preview_reviewed_studio_repairs
from skeleton.jeeves.game_complete_studio_quality_tools import complete_studio_quality_handlers
from skeleton.jeeves.game_studio_tools import StudioCommand, studio_command_catalog
from skeleton.testing.test_game_production_frontier_quality import candidate as frontier_candidate


SHA = "a" * 64
ALT = "b" * 64


def candidate():
    source = frontier_candidate()
    source["studio"] = {
        "source_sha256": SHA,
        "cinematics": {
            "source_sha256": SHA,
            "scenes": [{
                "id": "arrival", "fps": 60, "total_frames": 180,
                "shots": [
                    {"id": "establish", "start_frame": 0, "end_frame": 90,
                     "camera": "camera_a", "intent": "establish sky islands",
                     "near_m": 0.1, "far_m": 1000, "fov_deg": 70},
                    {"id": "closeup", "start_frame": 90, "end_frame": 180,
                     "camera": "camera_b", "intent": "hero recognizes the shore",
                     "near_m": 0.1, "far_m": 100, "fov_deg": 45},
                ],
            }],
        },
        "dialogue": {
            "source_sha256": SHA, "tolerance_ms": 40,
            "cues": [{
                "id": "hero_greeting", "start_ms": 100, "end_ms": 1100,
                "caption_start_ms": 110, "caption_end_ms": 1110,
                "caption": "The bridge is safe.", "has_voice": True,
                "voice_sha256": SHA, "phonemes": [
                    {"time_ms": 100}, {"time_ms": 230}, {"time_ms": 900},
                ],
            }],
        },
        "npcs": {
            "source_sha256": SHA,
            "agents": [{
                "id": "guide", "spawn_state": "idle", "states": [
                    {"id": "idle", "next": ["walk"], "timeout_s": 2,
                     "terminal": False},
                    {"id": "walk", "next": ["safety"], "timeout_s": 3,
                     "terminal": False},
                    {"id": "safety", "next": [], "timeout_s": 0,
                     "terminal": True},
                ],
            }],
        },
        "streaming": {
            "source_sha256": SHA, "max_chunk_bytes": 600,
            "max_resident_bytes": 1024, "entry_chunk": "harbor",
            "chunks": [
                {"id": "harbor", "bytes": 400, "sha256": SHA,
                 "neighbors": ["sky"], "requires": []},
                {"id": "sky", "bytes": 500, "sha256": ALT,
                 "neighbors": ["harbor"], "requires": ["harbor"]},
            ],
        },
        "saves": {
            "source_sha256": SHA, "current_version": 3,
            "supported_versions": [1, 2, 3],
            "migrations": [
                {"from_version": 1, "to_version": 2,
                 "transform_sha256": SHA, "input_sha256": SHA,
                 "output_sha256": ALT, "independently_replayed": True},
                {"from_version": 2, "to_version": 3,
                 "transform_sha256": ALT, "input_sha256": ALT,
                 "output_sha256": SHA, "independently_replayed": True},
            ],
        },
        "environment": {
            "source_sha256": SHA,
            "states": [
                {"id": "clear", "hazardous": False, "effect_sha256": SHA,
                 "transitions": [{"to": "storm", "probability": 1}]},
                {"id": "storm", "hazardous": True, "effect_sha256": ALT,
                 "mitigation": ["shelter"],
                 "transitions": [{"to": "clear", "probability": 1}]},
            ],
            "observations": [
                {"state": "clear", "effect_sha256": SHA,
                 "independently_replayed": True},
                {"state": "storm", "effect_sha256": ALT,
                 "independently_replayed": True},
            ],
        },
        "latency": {
            "source_sha256": SHA, "max_p95_ms": 24, "max_p99_ms": 30,
            "observations": [
                {"device": device, "source_sha256": SHA,
                 "input_ms": index * 30, "render_ack_ms": index * 30 + 10,
                 "observed": True}
                for device in ("keyboard", "gamepad") for index in range(20)
            ],
        },
    }
    return source


class ProductionStudioGateTests(unittest.TestCase):
    def test_27_gates_are_source_bound_canonical_and_not_releases(self):
        sample = candidate()
        result = audit_complete_studio(sample)
        self.assertEqual(27, len(result["gates"]))
        self.assertTrue(result["candidate_passed"])
        self.assertFalse(result["release_certified"])
        proof = verify_complete_studio(sample, result)
        self.assertEqual(27, proof["gate_count"])
        self.assertTrue(proof["source_recomputation"])
        self.assertEqual(27, verify_report_structure(result)["gate_count"])

    def test_cinematic_gaps_are_rejected(self):
        c = candidate()["studio"]["cinematics"]
        c["scenes"][0]["shots"][1]["start_frame"] = 91
        self.assertIn("timeline_gap_or_overlap",
                      {x.code for x in audit_cinematic_direction(c).findings})

    def test_cinematic_bad_camera_is_rejected(self):
        c = candidate()["studio"]["cinematics"]
        c["scenes"][0]["shots"][0]["fov_deg"] = 180
        self.assertFalse(audit_cinematic_direction(c).passed)

    def test_cinematic_missing_final_frames_are_rejected(self):
        c = candidate()["studio"]["cinematics"]
        c["scenes"][0]["shots"].pop()
        self.assertIn("incomplete_timeline",
                      {x.code for x in audit_cinematic_direction(c).findings})

    def test_dialogue_rejects_caption_drift(self):
        c = candidate()["studio"]["dialogue"]
        c["cues"][0]["caption_end_ms"] = 1900
        self.assertIn("caption_drift", {x.code for x in audit_dialogue_sync(c).findings})

    def test_dialogue_rejects_unhashed_voice(self):
        c = candidate()["studio"]["dialogue"]
        c["cues"][0]["voice_sha256"] = "unsigned"
        self.assertFalse(audit_dialogue_sync(c).passed)

    def test_dialogue_rejects_out_of_order_phonemes(self):
        c = candidate()["studio"]["dialogue"]
        c["cues"][0]["phonemes"][2]["time_ms"] = 200
        self.assertIn("phoneme_out_of_order",
                      {x.code for x in audit_dialogue_sync(c).findings})

    def test_npc_rejects_undefined_behavior_target(self):
        c = candidate()["studio"]["npcs"]
        c["agents"][0]["states"][0]["next"] = ["deleted"]
        self.assertIn("unknown_transition",
                      {x.code for x in audit_npc_behavior(c).findings})

    def test_npc_rejects_unreachable_terminal(self):
        c = candidate()["studio"]["npcs"]
        c["agents"][0]["states"][1]["next"] = ["idle"]
        self.assertIn("no_terminal_path",
                      {x.code for x in audit_npc_behavior(c).findings})

    def test_npc_rejects_unbounded_wait(self):
        c = candidate()["studio"]["npcs"]
        c["agents"][0]["states"][0]["timeout_s"] = 0
        self.assertIn("unbounded_wait",
                      {x.code for x in audit_npc_behavior(c).findings})

    def test_streaming_resident_neighbor_pressure(self):
        c = candidate()["studio"]["streaming"]
        c["max_resident_bytes"] = 800
        self.assertIn("resident_budget_exceeded",
                      {x.code for x in audit_world_streaming(c).findings})

    def test_streaming_rejects_foreign_dependencies(self):
        c = candidate()["studio"]["streaming"]
        c["chunks"][1]["requires"] = ["absent"]
        self.assertIn("missing_dependency",
                      {x.code for x in audit_world_streaming(c).findings})

    def test_streaming_rejects_missing_entry(self):
        c = candidate()["studio"]["streaming"]
        c["entry_chunk"] = "missing"
        self.assertFalse(audit_world_streaming(c).passed)

    def test_save_evolution_detects_migration_gap(self):
        c = candidate()["studio"]["saves"]
        c["migrations"].pop(0)
        self.assertIn("unsupported_upgrade",
                      {x.code for x in audit_save_evolution(c).findings})

    def test_save_evolution_rejects_unverified_transform(self):
        c = candidate()["studio"]["saves"]
        c["migrations"][0]["independently_replayed"] = False
        self.assertIn("unverified_transform",
                      {x.code for x in audit_save_evolution(c).findings})

    def test_save_evolution_disallows_unsigned_transform(self):
        c = candidate()["studio"]["saves"]
        c["migrations"][0]["transform_sha256"] = "bad"
        self.assertFalse(audit_save_evolution(c).passed)

    def test_weather_rejects_unmitigated_hazards(self):
        c = candidate()["studio"]["environment"]
        c["states"][1]["mitigation"] = []
        self.assertIn("unmitigated_hazard",
                      {x.code for x in audit_dynamic_world(c).findings})

    def test_weather_rejects_probabilities_not_summing_to_one(self):
        c = candidate()["studio"]["environment"]
        c["states"][0]["transitions"][0]["probability"] = 0.5
        self.assertIn("invalid_transition_weights",
                      {x.code for x in audit_dynamic_world(c).findings})

    def test_weather_requires_replayed_effects(self):
        c = candidate()["studio"]["environment"]
        c["observations"][1]["independently_replayed"] = False
        self.assertIn("unverified_world_effect",
                      {x.code for x in audit_dynamic_world(c).findings})

    def test_input_tail_rejects_latency_regressions(self):
        c = candidate()["studio"]["latency"]
        c["observations"][0]["render_ack_ms"] = 200
        self.assertIn("p99_exceeded",
                      {x.code for x in audit_controller_latency(c).findings})

    def test_input_requires_keyboard_and_gamepad(self):
        c = candidate()["studio"]["latency"]
        c["observations"] = [row for row in c["observations"]
                              if row["device"] == "keyboard"]
        self.assertIn("missing_device",
                      {x.code for x in audit_controller_latency(c).findings})

    def test_input_rejects_nonmonotone_clocks(self):
        c = candidate()["studio"]["latency"]
        c["observations"][1]["input_ms"] = -1
        with self.assertRaises(QualityGateError):
            audit_controller_latency(c)

    def test_all_seven_source_planes_fail_on_foreign_content(self):
        for name in ("cinematics", "dialogue", "npcs", "streaming",
                     "saves", "environment", "latency"):
            with self.subTest(name=name):
                c = candidate()
                c["studio"][name]["source_sha256"] = ALT
                with self.assertRaises(QualityGateError):
                    audit_complete_studio(c)

    def test_independent_composite_rejects_corrupted_gate_pass(self):
        c = candidate()
        report = audit_complete_studio(c)
        report["gates"][-1]["passed"] = False
        with self.assertRaises(QualityGateError):
            verify_complete_studio(c, report)


class StudioUpgradesTests(unittest.TestCase):
    def test_dragon_challenges_seven_planes_plus_two_forgery_lanes(self):
        result = challenge_studio_verifiers(candidate())
        self.assertEqual(7, result["mutations_count"])
        self.assertTrue(result["report_forgery_rejected"])
        self.assertTrue(result["summary_forgery_rejected"])
        self.assertFalse(result["weights_updated"])

    def test_dragon_refuses_known_incorrect_baseline(self):
        c = candidate()
        c["studio"]["cinematics"]["scenes"][0]["shots"].clear()
        with self.assertRaises(QualityGateError):
            challenge_studio_verifiers(c)

    def test_report_comparison_marks_critical_save_regression(self):
        a = audit_complete_studio(candidate())
        bad = candidate()
        bad["studio"]["saves"]["migrations"][0]["independently_replayed"] = False
        b = audit_complete_studio(bad)
        result = compare_studio_reports(a, b)
        self.assertTrue(result["critical_regression"])
        self.assertFalse(result["strict_pareto_improvement"])

    def test_objective_improvement_requires_no_other_regressions(self):
        failed = candidate()
        failed["studio"]["cinematics"]["scenes"][0]["shots"].pop()
        a = audit_complete_studio(failed)
        b = audit_complete_studio(candidate())
        result = compare_studio_reports(a, b)
        self.assertTrue(result["strict_pareto_improvement"])
        self.assertFalse(result["critical_regression"])

    def test_owner_queue_names_actual_game_authority_without_auto_edits(self):
        c = candidate()
        c["studio"]["streaming"]["chunks"][0]["bytes"] = 10000
        c["studio"]["cinematics"]["scenes"][0]["shots"].pop()
        work = studio_repair_queue(audit_complete_studio(c))
        self.assertEqual("P0", work["work_items"][0]["priority"])
        self.assertEqual("world_streaming_owner", work["work_items"][0]["owner"])
        self.assertTrue(all(not row["authorized_to_mutate"]
                            for row in work["work_items"]))

    def test_27_gate_reports_persist_with_existing_sqlite_history_and_resume(self):
        report = audit_complete_studio(candidate())
        with TemporaryDirectory() as root:
            db = Path(root) / "studio.db"
            with QualityHistoryStore(db) as store:
                r1 = store.append("game-1", report, expected_generation=0,
                                  expected_head="0" * 64)
                self.assertEqual(1, r1["generation"])
                self.assertEqual(report, store.report_at("game-1", generation=1))
            with QualityHistoryStore(db) as store:
                self.assertEqual(r1["head"], store.inspect("game-1")["head"])
                review = store.review(
                    "game-1", reviewer_id="operator-01",
                    decision="accept_candidate", reason_sha256=ALT,
                    report_head_sha256=r1["head"],
                    expected_generation=0, expected_head="0" * 64,
                )
                self.assertFalse(review["production_approved"])
                with self.assertRaises(QualityGateError):
                    store.review(
                        "game-1", reviewer_id="operator-01",
                        decision="accept_candidate", reason_sha256=ALT,
                        report_head_sha256=r1["head"],
                        expected_generation=0, expected_head="0" * 64,
                    )

    def test_eight_jeeves_actions_bind_source_cas_and_human_review(self):
        with TemporaryDirectory() as root:
            with QualityHistoryStore(Path(root) / "studio.db") as store:
                handlers = complete_studio_quality_handlers(
                    {"game-1": (SHA, candidate)}, store=store,
                    operator_id="operator-01",
                )
                self.assertEqual(8, len(handlers))
                catalog = studio_command_catalog()
                self.assertIn("game.studio.quality.dragon", catalog["read_operations"])
                self.assertIn("game.studio.quality.record", catalog["write_operations"])

                def run(op, payload=None, project="game-1"):
                    command = StudioCommand(op, project, payload or {})
                    return handlers[op](command, None)

                self.assertTrue(run("game.studio.quality.audit")["candidate_passed"])
                self.assertEqual(7, run("game.studio.quality.dragon")["mutations_count"])
                self.assertEqual([], run("game.studio.quality.work")["work_items"])
                first = run("game.studio.quality.record", {
                    "expected_generation": 0, "expected_head": "0" * 64,
                })
                self.assertEqual(1, first["generation"])
                self.assertEqual(1, run("game.studio.quality.history")["generation"])
                self.assertEqual([], run("game.studio.quality.diff", {
                    "prior_generation": 1,
                })["regressions"])
                review = run("game.studio.quality.review", {
                    "decision": "accept_candidate", "reason_sha256": ALT,
                    "report_head_sha256": first["head"],
                    "expected_generation": 0, "expected_head": "0" * 64,
                })
                self.assertFalse(review["production_approved"])
                with self.assertRaises(QualityGateError):
                    run("game.studio.quality.native.inspect")
                with self.assertRaises(QualityGateError):
                    run("game.studio.quality.audit", project="foreign")

    def test_native_receipt_rejects_mock_data_and_unowned_source(self):
        with self.assertRaises(QualityGateError):
            inspect_native_game_witness(candidate(), None, None, {}, {})
        with TemporaryDirectory() as root:
            with QualityHistoryStore(Path(root) / "studio.db") as store:
                handlers = complete_studio_quality_handlers(
                    {"game-1": (SHA, candidate)}, store=store,
                    operator_id="operator-01",
                    native_owners={"game-1": lambda: (None, None, {}, {})},
                )
                command = StudioCommand("game.studio.quality.native.inspect", "game-1", {})
                with self.assertRaises(QualityGateError):
                    handlers[command.operation](command, None)

    def test_reviewed_repair_only_accepts_measurably_improved_original(self):
        c = candidate()
        c["studio"]["cinematics"]["scenes"][0]["shots"][1]["intent"] = ""
        patch = {
            "path": ["studio", "cinematics", "scenes", 0, "shots", 1, "intent"],
            "old": "", "new": "arrival with long-term canon payoff",
        }
        result = preview_reviewed_studio_repairs(
            c, [patch], authorize=lambda p: True,
            independently_verify=lambda p: p["source_sha256"] == SHA,
        )
        self.assertEqual(1, result["accepted_count"])
        self.assertTrue(result["post_quality"]["candidate_passed"])
        self.assertFalse(result["persisted"])
        self.assertEqual("", c["studio"]["cinematics"]["scenes"][0]["shots"][1]["intent"])

    def test_reviewed_repair_cannot_forge_native_or_source_proofs(self):
        c = candidate()
        c["studio"]["environment"]["observations"][0]["independently_replayed"] = False
        patch = {
            "path": ["studio", "environment", "observations", 0, "independently_replayed"],
            "old": False, "new": True,
        }
        result = preview_reviewed_studio_repairs(
            c, [patch], authorize=lambda p: True,
            independently_verify=lambda p: True,
        )
        self.assertEqual(0, result["accepted_count"])
        self.assertFalse(result["post_quality"]["candidate_passed"])

    def test_preview_requires_host_approval_and_independent_compiler(self):
        c = candidate()
        c["studio"]["cinematics"]["scenes"][0]["shots"][1]["intent"] = ""
        patch = {
            "path": ["studio", "cinematics", "scenes", 0, "shots", 1, "intent"],
            "old": "", "new": "proofread cinematic closure",
        }
        denied = preview_reviewed_studio_repairs(
            c, [patch], authorize=lambda p: False,
            independently_verify=lambda p: True,
        )
        self.assertEqual("host_denied", denied["attempts"][0]["outcome"])
        refused = preview_reviewed_studio_repairs(
            c, [patch], authorize=lambda p: True,
            independently_verify=lambda p: False,
        )
        self.assertEqual(0, refused["accepted_count"])

    def test_jeeves_preview_is_an_isolated_nonpersistent_tool(self):
        c = candidate()
        c["studio"]["cinematics"]["scenes"][0]["shots"][1]["intent"] = ""
        with TemporaryDirectory() as root:
            with QualityHistoryStore(Path(root) / "studio.db") as store:
                handlers = complete_studio_quality_handlers(
                    {"game-1": (SHA, lambda: c)}, store=store,
                    operator_id="operator-01",
                    approve_patch=lambda command, patch: command.project_id == "game-1",
                    verify_candidate=lambda command, new: new["source_sha256"] == SHA,
                )
                self.assertEqual(9, len(handlers))
                command = StudioCommand("game.studio.quality.repair.preview", "game-1", {
                    "patches": [{
                        "path": ["studio", "cinematics", "scenes", 0, "shots", 1, "intent"],
                        "old": "", "new": "frame-coherent original direction",
                    }],
                })
                result = handlers[command.operation](command, None)
                self.assertEqual(1, result["accepted_count"])
                self.assertFalse(result["persisted"])
                self.assertFalse(store.inspect("game-1")["generation"])
                self.assertEqual("", c["studio"]["cinematics"]["scenes"][0]["shots"][1]["intent"])

    def test_27_gate_summary_tamper_is_rejected(self):
        report = audit_complete_studio(candidate())
        report["findings"] = [{"gate": "rights", "code": "imaginary", "subject": "X"}]
        with self.assertRaises(QualityGateError):
            verify_report_structure(report)


if __name__ == "__main__":
    unittest.main()
