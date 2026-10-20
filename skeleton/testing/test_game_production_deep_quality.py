"""Integrated acceptance for 13 original game quality milestones.

All fixtures are synthetic and explicitly distinguish unit validation from
native engine proof, external rights signoff and production release.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.game.production_quality import QualityGateError, _digest
from skeleton.game.production_deep_gates import (
    audit_deep_candidate, audit_design_traceability,
    audit_quest_ending_graph, audit_accessibility_ui, audit_input_parity,
    audit_resource_envelopes, audit_session_receipts, audit_package_closure,
    verify_deep_quality_report,
)
from skeleton.game.production_dragon_redteam import challenge_quality_verifiers
from skeleton.game.production_repair import suggest_quality_repairs, execute_reviewed_repairs
from skeleton.game.production_history import QualityHistoryStore
from skeleton.game.production_native_quality import _verify_sample_log
from skeleton.game.production_campaign_acceptance import accept_original_campaign
from skeleton.jeeves.game_production_quality_tools import game_quality_studio_handlers
from skeleton.jeeves.game_studio_tools import StudioCommand, studio_command_catalog

_A = "a" * 64
_B = "b" * 64


def candidate():
    event = {"sequence": 1, "previous": _A, "state_sha256": _B,
             "input": "move", "world": _A}
    event["receipt"] = _digest(event)
    controls = ("move", "interact", "confirm", "cancel", "pause")
    return {
        "source_sha256": _A,
        "world": {
            "nodes": [{"id": "camp"}, {"id": "exit"}],
            "edges": [{"from": "camp", "to": "exit"}],
            "start": "camp", "victory": "exit",
        },
        "story": {"cast": [{"id": "guide"}], "scenes": [
            {"id": "intro", "speakers": ["guide"]},
            {"id": "finale", "prerequisites": ["intro"], "speakers": ["guide"]},
        ]},
        "assets": [{"path": "meshes/original.obj", "sha256": _A, "bytes": 64}],
        "builds": [
            {"source_sha256": _A, "files": {"mesh": _B}},
            {"source_sha256": _A, "files": {"mesh": _B}},
        ],
        "frames": [{"ms": 4.0, "draw_calls": 12} for _ in range(100)],
        "sources": [{"id": "original", "origin": "original",
                     "reviewed": True, "evidence_ref": "host_review/001"}],
        "design": {"source_sha256": _A, "goals": [
            {"id": "playable", "mandatory": True},
            {"id": "accessible", "mandatory": True},
        ], "proofs": [
            {"goal": "playable", "source_sha256": _A,
             "artifact_sha256": _B, "observed": True},
            {"goal": "accessible", "source_sha256": _A,
             "artifact_sha256": _B, "observed": True},
        ]},
        "campaign": {
            "stages": [{"id": "begin"}, {"id": "finish", "requires": ["begin"]}],
            "endings": [{"id": "earned", "requires": ["finish"]}],
            "playthroughs": [{"ending": "earned", "completed": ["begin", "finish"],
                              "won": True}],
        },
        "screens": [{"id": "main", "subtitles": True,
                     "controls": [{"id": "start", "label": "Start",
                                   "focusable": True, "contrast_ratio": 7.0}]}],
        "profiles": [{"device": mode, "bindings": {
            a: mode + "_" + a for a in controls,
        }} for mode in ("keyboard", "gamepad")],
        "envelopes": [{"target": "portable", "ram_mb": 512,
                       "max_ram_mb": 1024, "texture_mb": 64,
                       "max_texture_mb": 128, "peak_streaming_mb": 25,
                       "max_peak_streaming_mb": 50, "load_ms": 700,
                       "max_load_ms": 1500}],
        "session": {"genesis": _A, "events": [event], "head": event["receipt"]},
        "package": {"entry": "main", "files": [
            {"id": "main", "sha256": _A, "imports": ["scene"]},
            {"id": "scene", "sha256": _B, "imports": []},
        ]},
    }


class GameProductionDeepTests(unittest.TestCase):
    def test_thirteen_gates_pass_without_release_certification(self):
        result = audit_deep_candidate(candidate())
        self.assertEqual(13, len(result["gates"]))
        self.assertTrue(result["candidate_passed"])
        self.assertFalse(result["release_certified"])
        self.assertEqual(_digest(result["gates"]), result["evidence_digest"])

    def test_traceability_missing_direct_proof(self):
        c = candidate()["design"]
        c["proofs"].pop()
        self.assertIn("unproven_goal", {f.code for f in audit_design_traceability(c).findings})

    def test_traceability_foreign_source(self):
        c = candidate()["design"]
        c["proofs"][0]["source_sha256"] = _B
        self.assertFalse(audit_design_traceability(c).passed)

    def test_quest_cycle_rejected(self):
        c = candidate()["campaign"]
        c["stages"][0]["requires"] = ["finish"]
        self.assertFalse(audit_quest_ending_graph(c).passed)

    def test_unearned_ending_rejected(self):
        c = candidate()["campaign"]
        c["playthroughs"][0]["completed"] = ["begin"]
        self.assertFalse(audit_quest_ending_graph(c).passed)

    def test_accessibility_missing_label(self):
        c = candidate()["screens"]
        c[0]["controls"][0]["label"] = ""
        self.assertFalse(audit_accessibility_ui(c).passed)

    def test_controller_missing_parity_and_collision(self):
        c = candidate()["profiles"]
        c.pop()
        self.assertFalse(audit_input_parity(c).passed)
        c = candidate()["profiles"]
        c[0]["bindings"]["pause"] = c[0]["bindings"]["cancel"]
        self.assertFalse(audit_input_parity(c).passed)

    def test_memory_load_and_texture_bounds(self):
        c = candidate()["envelopes"]
        c[0]["load_ms"] = 100000
        c[0]["ram_mb"] = 999999
        self.assertEqual(2, len(audit_resource_envelopes(c).findings))

    def test_session_tamper_rejected(self):
        c = candidate()["session"]
        c["events"][0]["input"] = "forge"
        self.assertFalse(audit_session_receipts(c).passed)

    def test_package_dependency_closure(self):
        c = candidate()["package"]
        c["files"][0]["imports"] = ["foreign"]
        self.assertIn("missing_dependency", {f.code for f in audit_package_closure(c).findings})

    def test_empty_sections_cannot_pass(self):
        for key in ("screens", "profiles", "envelopes"):
            c = candidate()
            c[key] = []
            self.assertFalse(audit_deep_candidate(c)["candidate_passed"], key)

    def test_dragon_challenges_all_thirteen_and_verifier(self):
        proof = challenge_quality_verifiers(candidate())
        self.assertEqual(13, len(proof["attacks"]))
        self.assertTrue(proof["all_challenges_rejected"])
        self.assertTrue(proof["summary_tamper_rejected"])
        self.assertFalse(proof["weights_trained"])
        self.assertFalse(proof["native_engine_executed"])

    def test_dragon_rejects_known_bad_baseline(self):
        c = candidate()
        c["sources"][0]["reviewed"] = False
        with self.assertRaises(QualityGateError):
            challenge_quality_verifiers(c)

    def test_repair_plan_routes_to_real_owner(self):
        c = candidate()
        c["sources"][0]["reviewed"] = False
        report = suggest_quality_repairs(audit_deep_candidate(c))
        self.assertEqual("human_rights_reviewer", report["actions"][0]["responsible_owner"])
        self.assertEqual(0, report["automatic_edits"])

    def test_repair_applies_only_authorized_improvement_in_memory(self):
        c = candidate()
        c["screens"][0]["controls"][0]["label"] = ""
        patch = {"path": ["screens", 0, "controls", 0, "label"],
                 "old": "", "new": "Start"}
        result = execute_reviewed_repairs(
            c, [patch], authorize=lambda p: True,
            verify_source=lambda obj: obj["source_sha256"] == _A,
        )
        self.assertEqual(1, result["accepted"])
        self.assertTrue(result["candidate_report"]["candidate_passed"])
        self.assertEqual("", c["screens"][0]["controls"][0]["label"])
        self.assertFalse(result["persisted"])

    def test_repair_never_forges_source_or_rights(self):
        c = candidate()
        c["sources"][0]["reviewed"] = False
        patch = {"path": ["sources", 0, "reviewed"], "old": False, "new": True}
        result = execute_reviewed_repairs(
            c, [patch], authorize=lambda p: True, verify_source=lambda p: True,
        )
        self.assertEqual(0, result["accepted"])
        self.assertFalse(result["candidate_report"]["candidate_passed"])

    def test_store_atomic_cas_and_restart(self):
        report = audit_deep_candidate(candidate())
        with TemporaryDirectory() as directory:
            dbpath = Path(directory) / "quality.sqlite"
            with QualityHistoryStore(dbpath) as store:
                initial = store.inspect("project-1")
                first = store.append("project-1", report, expected_generation=0,
                                     expected_head=initial["head"])
                self.assertEqual(1, first["generation"])
                with self.assertRaises(QualityGateError):
                    store.append("project-1", report, expected_generation=0,
                                 expected_head=initial["head"])
                second = store.append("project-1", report, expected_generation=1,
                                      expected_head=first["head"])
                self.assertEqual(2, second["generation"])
            with QualityHistoryStore(dbpath) as store:
                self.assertEqual(second["head"], store.inspect("project-1")["head"])
                self.assertEqual(2, len(store.history("project-1")["entries"]))
                with self.assertRaises(QualityGateError):
                    store.inspect("project-1", expected_head=_A)

    def test_store_rejects_tampered_history(self):
        report = audit_deep_candidate(candidate())
        with TemporaryDirectory() as directory:
            with QualityHistoryStore(Path(directory) / "quality.sqlite") as store:
                initial = store.inspect("project-1")
                store.append("project-1", report, expected_generation=0,
                             expected_head=initial["head"])
                store.db.execute("UPDATE quality_evidence SET receipt_sha256=?",
                                 (_A,))
                with self.assertRaises(QualityGateError):
                    store.inspect("project-1")

    def test_jeeves_host_authorizer_catalog_and_real_handlers(self):
        with TemporaryDirectory() as directory:
            with QualityHistoryStore(Path(directory) / "audit.sqlite") as store:
                handlers = game_quality_studio_handlers(
                    {"project-1": (_A, candidate)}, store=store)
                catalog = studio_command_catalog()
                self.assertIn("game.quality.audit", catalog["read_operations"])
                self.assertIn("game.quality.record", catalog["write_operations"])
                base = StudioCommand("game.quality.audit", "project-1", {})
                self.assertTrue(handlers[base.operation](base, None)["candidate_passed"])
                command = StudioCommand("game.quality.record", "project-1", {
                    "expected_generation": 0, "expected_head": "0" * 64,
                })
                self.assertEqual(1, handlers[command.operation](command, None)["generation"])
                hist = StudioCommand("game.quality.history", "project-1", {"limit": 1})
                self.assertEqual(1, len(handlers[hist.operation](hist, None)["entries"]))
                chall = StudioCommand("game.quality.challenge", "project-1", {})
                self.assertTrue(handlers[chall.operation](chall, None)["all_challenges_rejected"])
                with self.assertRaises(QualityGateError):
                    other = StudioCommand("game.quality.audit", "alien", {})
                    handlers[other.operation](other, None)

    def test_independent_verifier_catches_forged_summary(self):
        c = candidate()
        report = audit_deep_candidate(c)
        self.assertTrue(verify_deep_quality_report(c, report)["independent_replay_passed"])
        bad = dict(report)
        bad["candidate_passed"] = False
        with self.assertRaises(QualityGateError):
            verify_deep_quality_report(c, bad)

    def test_package_cycles_are_rejected(self):
        c = candidate()["package"]
        c["files"][1]["imports"] = ["main"]
        self.assertIn("dependency_cycle",
                      {f.code for f in audit_package_closure(c).findings})

    def test_long_quest_chains_are_bounded_without_recursive_stack(self):
        c = candidate()["campaign"]
        c["stages"] = [{"id": "step" + str(i),
                        "requires": ["step" + str(i - 1)] if i else []}
                       for i in range(2000)]
        c["endings"] = [{"id": "earned", "requires": ["step1999"]}]
        c["playthroughs"] = [{
            "ending": "earned", "completed": ["step" + str(i) for i in range(2000)],
            "won": True,
        }]
        self.assertTrue(audit_quest_ending_graph(c).passed)

    def test_native_sampler_rejects_fake_missing_or_reordered_samples(self):
        lines = []
        for i in range(30):
            record = {"frame": i, "process_ms": 1.0, "draw_calls": 0,
                      "engine": 4, "renderer": "headless_unattested"}
            lines.append("SKELETON_GAME_QUALITY " + json.dumps(record))
        self.assertEqual(30, len(_verify_sample_log("\n".join(lines), 30)))
        with self.assertRaises(QualityGateError):
            _verify_sample_log("\n".join(lines[:-1]), 30)
        with self.assertRaises(QualityGateError):
            _verify_sample_log("\n".join(reversed(lines)), 30)

    def test_campaign_rejects_unowned_or_noncanonical_source(self):
        with self.assertRaises(QualityGateError):
            accept_original_campaign({}, {}, {}, {}, [])


if __name__ == "__main__":
    unittest.main()
