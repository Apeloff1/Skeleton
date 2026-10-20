"""Regression suite for 50 new original-game production milestones.

Each domain has a separate executable mutation test. Synthetic evidence tests
contract behavior, never native hardware, GPU, rights or year-long runs.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.game.production_quality import QualityGateError
from skeleton.game.production_advanced_assurance import GATES_34
from skeleton.game.production_expanded_gates import (
    SPECS, NAMES, audit_expanded_studio, verify_expanded_studio,
)
from skeleton.game.production_expanded_assurance import (
    verify_84_structure, compare_84, queue_84, impact_84,
)
from skeleton.game.production_expanded_dragon import challenge_84_verifiers
from skeleton.game.production_history import QualityHistoryStore
from skeleton.jeeves.game_expanded_studio_quality_tools import expanded_studio_quality_handlers
from skeleton.jeeves.game_studio_tools import StudioCommand, studio_command_catalog
from skeleton.testing.test_game_production_advanced_quality import candidate as earlier_candidate

SHA = "a" * 64
ALT = "b" * 64
GENESIS = "0" * 64


def candidate():
    result = earlier_candidate()
    expanded = {"source_sha256": SHA}
    for spec in SPECS:
        if spec.mode == "timing":
            payload = {"samples": [
                {"id": f"{spec.name}:{i}", "start_ms": 100 * i,
                 "end_ms": 100 * i + 50, "target_end_ms": 100 * i + 50,
                 "source_sha256": SHA, "capture_sha256": ALT,
                 "independently_observed": True}
                for i in range(3)
            ]}
        elif spec.mode == "physics":
            payload = {"samples": [
                {"id": f"{spec.name}:{i}", "unit": spec.unit,
                 "expected": 10, "measured": 10, "replayed": 10,
                 "replay_independent": True, "source_sha256": SHA,
                 "capture_sha256": ALT, "independently_observed": True}
                for i in range(3)
            ]}
        elif spec.mode == "graph":
            payload = {
                "entry": "entry",
                "nodes": [
                    {"id": name, "next": children, "terminal": end,
                     "canon_sha256": SHA, "capture_sha256": ALT,
                     "source_sha256": SHA, "independently_observed": True}
                    for name, children, end in (
                        ("entry", ["middle"], False),
                        ("middle", ["ending"], False),
                        ("ending", [], True),
                    )
                ],
            }
        elif spec.mode == "asset":
            payload = {
                "max_asset_bytes": 4096,
                "assets": [
                    {"id": f"{spec.name}:{i}", "unit": spec.unit,
                     "deviation": 0, "bytes": 1024,
                     "original_sha256": SHA, "rendered_sha256": ALT,
                     "source_sha256": SHA, "capture_sha256": ALT,
                     "independently_observed": True,
                     "provenance_reviewed": True}
                    for i in range(2)
                ],
            }
        else:
            payload = {"attempts": [
                {"id": f"{spec.name}:{i}", "generation": i + 1,
                 "before_sha256": SHA, "after_sha256": SHA,
                 "replay_sha256": SHA, "receipt_sha256": ALT,
                 "source_sha256": SHA, "capture_sha256": ALT,
                 "elapsed_ms": 1, "independently_replayed": True,
                 "independently_observed": True}
                for i in range(3)
            ]}
        expanded[spec.name] = {"source_sha256": SHA, **payload}
    result["studio"]["expanded"] = expanded
    return result


def corrupt_domain(result, spec):
    payload = result["studio"]["expanded"][spec.name]
    if spec.mode == "timing":
        payload["samples"][0]["target_end_ms"] = 10000
    elif spec.mode == "physics":
        payload["samples"][0]["measured"] = 1000
    elif spec.mode == "graph":
        payload["nodes"][0]["next"] = ["nonexistent"]
    elif spec.mode == "asset":
        payload["assets"][0]["deviation"] = spec.threshold + 100
    else:
        payload["attempts"][0]["replay_sha256"] = "f" * 64


class ExpandedStudioAcceptance(unittest.TestCase):
    def test_84_gates_preserve_canonical_34_and_noncertification(self):
        bundle = candidate()
        report = audit_expanded_studio(bundle)
        self.assertTrue(report["candidate_passed"])
        self.assertFalse(report["release_certified"])
        self.assertEqual(84, len(report["gates"]))
        self.assertEqual(GATES_34, tuple(g["name"] for g in report["gates"][:34]))
        self.assertEqual(NAMES, tuple(g["name"] for g in report["gates"][34:]))
        self.assertEqual(84, verify_expanded_studio(bundle, report)["gate_count"])
        self.assertEqual(84, verify_84_structure(report)["gate_count"])

    def test_all_fifty_require_owner_source_identity(self):
        for spec in SPECS:
            with self.subTest(gate=spec.name):
                bundle = candidate()
                bundle["studio"]["expanded"][spec.name]["source_sha256"] = ALT
                with self.assertRaises(QualityGateError):
                    audit_expanded_studio(bundle)

    def test_forged_gate_and_summary_rejected(self):
        c = candidate()
        report = audit_expanded_studio(c)
        report["gates"][-1]["passed"] = False
        with self.assertRaises(QualityGateError):
            verify_84_structure(report)
        with self.assertRaises(QualityGateError):
            verify_expanded_studio(c, report)

    def test_fifty_dragon_rejections_plus_forged_report_probes(self):
        witnessed = challenge_84_verifiers(candidate())
        self.assertEqual(50, witnessed["rejected_count"])
        self.assertTrue(witnessed["source_forgery_rejected"])
        self.assertTrue(witnessed["summary_forgery_rejected"])
        self.assertFalse(witnessed["production_certified"])

    def test_queue_and_objective_comparison_never_authorize_edits(self):
        good = audit_expanded_studio(candidate())
        damaged = candidate()
        spec = next(s for s in SPECS if s.name == "adversarial_promotion")
        corrupt_domain(damaged, spec)
        bad = audit_expanded_studio(damaged)
        change = compare_84(good, bad)
        self.assertFalse(change["strict_pareto_improvement"])
        queue = queue_84(bad)
        self.assertEqual("verification_owner", queue["items"][0]["owner"])
        self.assertFalse(queue["items"][0]["mutation_authorized"])
        self.assertFalse(impact_84(bad)["mutation_authorized"])

    def test_84_gates_persist_with_earlier_schemas(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "studio.db"
            report = audit_expanded_studio(candidate())
            with QualityHistoryStore(path) as store:
                committed = store.append(
                    "project", report,
                    expected_generation=0, expected_head=GENESIS)
                self.assertEqual(1, committed["generation"])
                self.assertEqual(report, store.report_at("project", generation=1))
                with self.assertRaises(QualityGateError):
                    store.append("project", report,
                                 expected_generation=0, expected_head=GENESIS)
            with QualityHistoryStore(path) as reopened:
                self.assertEqual(1, reopened.inspect("project")["generation"])

    def test_jeeves_host_authorized_eight_operations(self):
        c = candidate()
        with TemporaryDirectory() as root:
            with QualityHistoryStore(Path(root) / "studio.db") as store:
                handlers = expanded_studio_quality_handlers(
                    {"original": (SHA, lambda: c)},
                    store=store, operator_id="reviewer-1",
                )
                self.assertEqual(8, len(handlers))
                commands = studio_command_catalog()
                self.assertIn("game.studio.expanded.audit", commands["read_operations"])
                self.assertIn("game.studio.expanded.record", commands["write_operations"])
                audit = StudioCommand("game.studio.expanded.audit", "original", {})
                self.assertTrue(handlers[audit.operation](audit, None)["candidate_passed"])
                record = StudioCommand("game.studio.expanded.record", "original", {
                    "expected_generation": 0, "expected_head": GENESIS})
                self.assertEqual(1, handlers[record.operation](record, None)["generation"])
                compare = StudioCommand("game.studio.expanded.diff", "original", {
                    "prior_generation": 1})
                self.assertFalse(handlers[compare.operation](compare, None)["regressed"])
                foreign = StudioCommand("game.studio.expanded.audit", "foreign", {})
                with self.assertRaises(QualityGateError):
                    handlers[audit.operation](foreign, None)

    def test_graph_cycle_without_terminal_path_rejected(self):
        c = candidate()
        p = c["studio"]["expanded"]["quest_dependency"]["nodes"]
        p[1]["next"] = ["entry"]
        report = audit_expanded_studio(c)
        codes = [f["code"] for f in report["findings"] if f["gate"] == "quest_dependency"]
        self.assertIn("unresolved_story_state", codes)

    def test_integrity_discontinuous_state_chain_rejected(self):
        c = candidate()
        c["studio"]["expanded"]["save_rollback"]["attempts"][1]["before_sha256"] = ALT
        report = audit_expanded_studio(c)
        codes = [f["code"] for f in report["findings"] if f["gate"] == "save_rollback"]
        self.assertIn("broken_transition_chain", codes)

    def test_backend_runtime_learning_identity_keeps_layer_boundary(self):
        from skeleton.contracts import runtime_learning_core as canonical
        from skeleton.intelligence import runtime_learning as compatibility
        from skeleton.persistence.execution_repository import SQLiteExecutionRepository
        self.assertIs(canonical, compatibility)
        self.assertTrue(callable(SQLiteExecutionRepository))
        self.assertEqual(canonical.normalize_policy(), compatibility.normalize_policy())


def _make_milestone_test(spec):
    def test(self):
        c = candidate()
        corrupt_domain(c, spec)
        report = audit_expanded_studio(c)
        gate = next(g for g in report["gates"] if g["name"] == spec.name)
        self.assertFalse(gate["passed"], spec.name)
        self.assertFalse(report["candidate_passed"])
    return test


for _spec in SPECS:
    setattr(ExpandedStudioAcceptance, "test_milestone_" + _spec.name,
            _make_milestone_test(_spec))


if __name__ == "__main__":
    unittest.main()
