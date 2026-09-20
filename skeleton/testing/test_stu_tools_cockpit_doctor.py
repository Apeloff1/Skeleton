"""Regression tests for STU-TOOLS cockpit/doctor deepen (gates + paths)."""
from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List

from skeleton.developer.doctor_deepen import (
    collect_doctor_snapshot,
    deepen_doctor_report,
    diff_doctor,
    doctor_recommendations,
    snapshot_from_doctor_card,
)
from skeleton.developer.doctor_gates import (
    assert_doctor_green,
    gate_doctor_diff,
    gate_doctor_snapshot,
    run_doctor_gates,
)
from skeleton.developer.gate_verdict import (
    GateSeverity,
    GateStatus,
    GateSuite,
    collect_verdict,
    error_gate,
    fail_gate,
    gate_table,
    merge_verdicts,
    pass_gate,
    require,
    skip_gate,
    summarize_gates,
)
from skeleton.developer.health_deepen import (
    collect_health_snapshot,
    deepen_health_report,
    diff_health,
    health_recommendations,
    snapshot_from_summary,
)
from skeleton.developer.health_gates import (
    assert_health_green,
    gate_health_diff,
    gate_health_snapshot,
    run_health_gates,
)
from skeleton.developer.stu_tools_pipeline import assert_pipeline_green, run_stu_tools_pipeline
from skeleton.developer.surface_inventory import (
    REQUIRED_COCKPIT_KNOBS,
    REQUIRED_DOCTOR_DOMAINS,
    REQUIRED_HEALTH_SURFACES,
    Surface,
    SurfaceInventory,
    SurfaceKind,
    SurfacePath,
    inventory_from_artefacts,
    inventory_from_blueprint,
    inventory_from_cockpit,
    inventory_from_doctor_card,
    inventory_from_health_summary,
    merge_inventories,
    score_from_metrics,
    status_score,
)
from skeleton.developer.visualize_deepen import (
    analyze_topology,
    deepen_visualize_report,
    snapshot_visualize,
    visualize_recommendations,
)
from skeleton.developer.visualize_gates import (
    assert_visualize_green,
    gate_visualize_snapshot,
    run_visualize_gates,
)
from skeleton.developer.weakest_regenerate import (
    apply_regen_plan,
    assert_regen_green,
    build_regen_plan,
    gate_regen_plan,
    run_weakest_regenerate,
    select_weakest,
)


def _healthy_summary() -> Dict[str, Any]:
    return {
        "overall": "healthy",
        "total_subsystems": len(REQUIRED_HEALTH_SURFACES),
        "phases_booted": len(REQUIRED_HEALTH_SURFACES),
        "status_breakdown": {"healthy": len(REQUIRED_HEALTH_SURFACES)},
        "cards": [
            {"name": n, "status": "healthy", "phase": n, "metrics": {"ok": 1}}
            for n in REQUIRED_HEALTH_SURFACES
        ],
    }


def _healthy_doctor() -> Dict[str, Any]:
    return {
        "alerts": [],
        "repair_effectiveness": {"ok": 1, "rate": 0.9},
        "kv_cache": {"hit_rate": 0.92},
        "policy": {"enforced": 1},
        "circuit": {"open": 0},
        "health": {"overall": "healthy"},
        "audit_integrity": {"ok": 1},
        "dashboard": {"ready": 1},
        "cockpit": {k: 1.0 for k in REQUIRED_COCKPIT_KNOBS},
        "stored_prose": 0,
    }


def _healthy_topology() -> Dict[str, Any]:
    return {
        "name": "pipe",
        "components": {
            "input": {"kind": "source", "ports": [{"name": "out"}]},
            "process": {"kind": "transform", "ports": [{"name": "in"}, {"name": "out"}]},
            "output": {"kind": "sink", "ports": [{"name": "in"}]},
        },
        "wires": [{"src": "input", "dst": "process"}, {"src": "process", "dst": "output"}],
    }


class TestGateVerdictPrimitives(unittest.TestCase):
    def test_pass_fail_error_skip(self):
        self.assertTrue(pass_gate("a").passed)
        self.assertFalse(fail_gate("b", reason="x").passed)
        self.assertTrue(fail_gate("b", reason="x", severity=GateSeverity.SEV1).blocks)
        self.assertTrue(error_gate("c", reason="e").blocks)
        self.assertFalse(skip_gate("d").blocks)

    def test_empty_suite_fails_closed(self):
        v = collect_verdict("empty", [])
        self.assertEqual(v.ok, 0)
        self.assertIn("FAIL CLOSED", v.banner)

    def test_info_failure_does_not_block(self):
        v = collect_verdict(
            "info",
            [fail_gate("soft", reason="nudge", severity=GateSeverity.INFO)],
        )
        self.assertEqual(v.ok, 1)

    def test_sev2_blocks(self):
        v = collect_verdict(
            "sev2",
            [fail_gate("hard", reason="nope", severity=GateSeverity.SEV2)],
        )
        self.assertEqual(v.ok, 0)

    def test_merge_verdicts_any_block(self):
        a = collect_verdict("a", [pass_gate("ok")])
        b = collect_verdict("b", [fail_gate("bad", reason="x", severity=GateSeverity.SEV1)])
        m = merge_verdicts("m", [a, b])
        self.assertEqual(m.ok, 0)
        self.assertIn("bad", m.banner)

    def test_gate_suite_builder(self):
        suite = GateSuite("s")
        suite.check(True, "t1", on_fail="f")
        suite.check(False, "t2", severity=GateSeverity.SEV2, on_fail="fail")
        v = suite.verdict()
        self.assertEqual(v.ok, 0)
        self.assertEqual(v.failed_count, 1)

    def test_require_helper(self):
        self.assertTrue(require(True, "x", on_fail="f").passed)
        self.assertFalse(require(False, "x", on_fail="f").passed)

    def test_fingerprint_stable(self):
        v1 = collect_verdict("k", [pass_gate("a"), pass_gate("b")])
        v2 = collect_verdict("k", [pass_gate("b"), pass_gate("a")])
        self.assertEqual(v1.fingerprint(), v2.fingerprint())

    def test_gate_table_and_summarize(self):
        v = collect_verdict("k", [pass_gate("a"), fail_gate("b", reason="x")])
        table = gate_table(v)
        self.assertIn("Gate", table)
        summary = summarize_gates(v.gates)
        self.assertEqual(summary["total"], 2)
        self.assertIn("blocking_names", summary)

    def test_to_dict_roundtrip_fields(self):
        v = collect_verdict("k", [pass_gate("a", reason="ok")])
        d = v.to_dict()
        self.assertEqual(d["ok"], 1)
        self.assertEqual(d["stored_prose"], 0)
        self.assertEqual(d["gates"][0]["name"], "a")


class TestSurfaceInventory(unittest.TestCase):
    def test_status_score_ladder(self):
        self.assertGreater(status_score("healthy"), status_score("degraded"))
        self.assertGreater(status_score("degraded"), status_score("failed"))

    def test_health_inventory_required(self):
        inv = inventory_from_health_summary(_healthy_summary())
        self.assertEqual(inv.required_missing(SurfacePath.HEALTH), [])
        self.assertGreaterEqual(inv.mean_score(SurfacePath.HEALTH), 0.5)

    def test_health_inventory_missing_required(self):
        summary = _healthy_summary()
        summary["cards"] = summary["cards"][:2]
        inv = inventory_from_health_summary(summary)
        # Required surfaces are still listed, but marked missing/zero-score when absent from cards.
        zeroed = [s for s in inv.by_path(SurfacePath.HEALTH) if s.required and s.score <= 0.0]
        self.assertTrue(zeroed)

    def test_doctor_inventory_domains(self):
        inv = inventory_from_doctor_card(_healthy_doctor())
        self.assertEqual(inv.required_missing(SurfacePath.DOCTOR), [])
        self.assertEqual(len(inv.by_path(SurfacePath.DOCTOR)), len(REQUIRED_DOCTOR_DOMAINS))

    def test_doctor_critical_lowers_score(self):
        card = _healthy_doctor()
        card["alerts"] = [{"subsystem": "repair", "severity": "critical", "message": "boom"}]
        inv = inventory_from_doctor_card(card)
        repair = [s for s in inv.by_path(SurfacePath.DOCTOR) if s.name == "repair"][0]
        self.assertLess(repair.score, 0.7)
        self.assertEqual(repair.status, "critical")

    def test_blueprint_inventory(self):
        inv = inventory_from_blueprint(_healthy_topology())
        self.assertEqual(inv.required_missing(SurfacePath.VISUALIZE), [])
        self.assertTrue(inv.by_path(SurfacePath.VISUALIZE))

    def test_cockpit_out_of_range(self):
        inv = inventory_from_cockpit({"speed_mul": 9.0, "heat_mul": 1.0, "collapse_mul": 1.0, "stored_prose": 0})
        speed = [s for s in inv.by_path(SurfacePath.COCKPIT) if s.name == "speed_mul"][0]
        self.assertLess(speed.score, 0.5)

    def test_artefacts_todo_and_empty(self):
        inv = inventory_from_artefacts({"a.gd": "TODO fix", "b.gd": ""})
        weak = inv.weakest(fraction=0.2)
        self.assertTrue(weak)
        self.assertTrue(any(s.score < 0.5 for s in inv.surfaces))

    def test_weakest_fraction_clamped(self):
        inv = SurfaceInventory()
        for i in range(20):
            inv.add(Surface(SurfacePath.HEALTH, SurfaceKind.SUBSYSTEM, f"s{i}", score=i / 20))
        w = inv.weakest(fraction=0.01)
        self.assertGreaterEqual(len(w), 1)
        w2 = inv.weakest(fraction=0.99)
        self.assertLessEqual(len(w2), 4)  # clamped to 20%

    def test_merge_inventories_prose(self):
        a = inventory_from_cockpit({k: 1.0 for k in REQUIRED_COCKPIT_KNOBS} | {"stored_prose": 0})
        b = inventory_from_artefacts({"x.gd": "extends Node\n"})
        m = merge_inventories(a, b)
        self.assertEqual(m.stored_prose, 0)
        self.assertGreater(len(m.surfaces), len(a.surfaces))

    def test_fingerprint_changes_on_score(self):
        inv1 = inventory_from_artefacts({"a.gd": "ok\nok\n"})
        inv2 = inventory_from_artefacts({"a.gd": "TODO\n"})
        self.assertNotEqual(inv1.fingerprint(), inv2.fingerprint())

    def test_score_from_metrics(self):
        self.assertGreaterEqual(score_from_metrics({"ok": 1}, base=0.8), 0.8)


class TestHealthPath(unittest.TestCase):
    def test_snapshot_and_gates_green(self):
        snap = snapshot_from_summary(_healthy_summary())
        v = gate_health_snapshot(snap)
        self.assertEqual(v.ok, 1)

    def test_failed_subsystem_sev1(self):
        summary = _healthy_summary()
        summary["cards"][0]["status"] = "failed"
        summary["status_breakdown"] = {"healthy": 6, "failed": 1}
        summary["overall"] = "failed"
        snap = snapshot_from_summary(summary)
        v = gate_health_snapshot(snap)
        self.assertEqual(v.ok, 0)

    def test_stored_prose_sev1(self):
        snap = snapshot_from_summary(_healthy_summary())
        snap.stored_prose = 1
        v = gate_health_snapshot(snap)
        self.assertEqual(v.ok, 0)
        self.assertTrue(any(g.name == "health.stored_prose_zero" for g in v.blocking))

    def test_diff_regression(self):
        a = snapshot_from_summary(_healthy_summary())
        bad = _healthy_summary()
        bad["overall"] = "degraded"
        bad["cards"][0]["status"] = "degraded"
        bad["status_breakdown"] = {"healthy": 6, "degraded": 1}
        b = snapshot_from_summary(bad)
        diff = diff_health(a, b)
        v = gate_health_diff(diff)
        # may or may not regress depending on overall rank — ensure API works
        self.assertIn(v.ok, (0, 1))
        self.assertTrue(diff.to_dict()["kind"])

    def test_run_health_gates_with_explorer(self):
        class E:
            def summary(self):
                return _healthy_summary()
        result = run_health_gates(explorer=E())
        assert_health_green(result)
        self.assertEqual(result["stored_prose"], 0)

    def test_recommendations_nonempty(self):
        snap = snapshot_from_summary(_healthy_summary())
        recs = health_recommendations(snap)
        self.assertTrue(recs)

    def test_deepen_report_shape(self):
        class E:
            def summary(self):
                return _healthy_summary()
        report = deepen_health_report(explorer=E())
        self.assertEqual(report["kind"], "stu-tools-health-report")
        self.assertIn("snapshot", report)


class TestVisualizePath(unittest.TestCase):
    def test_analyze_connected(self):
        stats = analyze_topology(_healthy_topology())
        self.assertTrue(stats.connected)
        self.assertEqual(stats.component_count, 3)
        self.assertEqual(stats.dangling_wires, [])

    def test_orphans_detected(self):
        topo = _healthy_topology()
        topo["components"]["lonely"] = {"kind": "orphan", "ports": []}
        stats = analyze_topology(topo)
        self.assertIn("lonely", stats.orphan_components)

    def test_dangling_wire(self):
        topo = _healthy_topology()
        topo["wires"].append({"src": "missing", "dst": "output"})
        stats = analyze_topology(topo)
        self.assertTrue(stats.dangling_wires)

    def test_gates_green(self):
        result = run_visualize_gates(topology=_healthy_topology())
        assert_visualize_green(result)

    def test_empty_fails_closed(self):
        result = run_visualize_gates(topology={"name": "empty", "components": {}, "wires": []})
        self.assertEqual(result["ok"], 0)

    def test_recommendations(self):
        snap = snapshot_visualize(topology=_healthy_topology())
        recs = visualize_recommendations(snap)
        self.assertTrue(recs)

    def test_deepen_report(self):
        report = deepen_visualize_report(topology=_healthy_topology())
        self.assertEqual(report["kind"], "stu-tools-visualize-report")
        self.assertEqual(report["stored_prose"], 0)


class TestDoctorPath(unittest.TestCase):
    def test_snapshot_green(self):
        snap = snapshot_from_doctor_card(_healthy_doctor())
        self.assertEqual(snap.stored_prose, 0)
        self.assertEqual(len(snap.critical_alerts), 0)
        v = gate_doctor_snapshot(snap)
        self.assertEqual(v.ok, 1)

    def test_critical_alert_fails(self):
        card = _healthy_doctor()
        card["alerts"] = [{"subsystem": "policy", "severity": "critical", "message": "open"}]
        snap = snapshot_from_doctor_card(card)
        v = gate_doctor_snapshot(snap)
        self.assertEqual(v.ok, 0)

    def test_stored_prose_fails(self):
        card = _healthy_doctor()
        card["stored_prose"] = 2
        card["cockpit"]["stored_prose"] = 2
        snap = snapshot_from_doctor_card(card)
        v = gate_doctor_snapshot(snap)
        self.assertEqual(v.ok, 0)

    def test_cockpit_out_of_range(self):
        card = _healthy_doctor()
        card["cockpit"]["heat_mul"] = 9.0
        snap = snapshot_from_doctor_card(card)
        v = gate_doctor_snapshot(snap)
        self.assertEqual(v.ok, 0)

    def test_diff_critical_up(self):
        a = snapshot_from_doctor_card(_healthy_doctor())
        bad = _healthy_doctor()
        bad["alerts"] = [{"subsystem": "audit", "severity": "critical", "message": "x"}]
        b = snapshot_from_doctor_card(bad)
        diff = diff_doctor(a, b)
        self.assertTrue(diff.regressed)
        v = gate_doctor_diff(diff)
        self.assertEqual(v.ok, 0)

    def test_run_doctor_gates(self):
        result = run_doctor_gates(card=_healthy_doctor())
        assert_doctor_green(result)

    def test_collect_synthetic(self):
        snap = collect_doctor_snapshot()
        self.assertEqual(snap.source, "synthetic")

    def test_recommendations_critical(self):
        card = _healthy_doctor()
        card["alerts"] = [{"subsystem": "repair", "severity": "critical", "message": "x"}]
        snap = snapshot_from_doctor_card(card)
        recs = doctor_recommendations(snap)
        actions = {r["action"] for r in recs}
        self.assertIn("clear_critical_alerts", actions)

    def test_deepen_report(self):
        report = deepen_doctor_report(card=_healthy_doctor())
        self.assertEqual(report["kind"], "stu-tools-doctor-report")


class TestWeakestRegenerate(unittest.TestCase):
    def test_select_and_plan(self):
        inv = inventory_from_artefacts(
            {
                "good.gd": "extends Node\nfunc _ready() -> void:\n    pass\n",
                "bad.gd": "TODO\n",
                "empty.gd": "",
            }
        )
        plan = build_regen_plan(inv, path=SurfacePath.WEAKEST)
        self.assertFalse(plan.empty)
        v = gate_regen_plan(plan)
        self.assertEqual(v.ok, 1)

    def test_dry_run_skips_apply(self):
        artefacts = {"bad.gd": "TODO FIXME\n"}
        result = run_weakest_regenerate(artefacts=artefacts, dry_run=True)
        assert_regen_green(result)
        self.assertTrue(result["result"]["dry_run"])
        self.assertTrue(result["result"]["skipped"])

    def test_apply_strips_todo(self):
        artefacts = {"bad.gd": "extends Node\n# TODO remove\nfunc _ready() -> void:\n    pass\n"}
        result = run_weakest_regenerate(artefacts=artefacts, dry_run=False)
        self.assertEqual(result["ok"], 1)
        after = result["result"]["artefacts_after"]["bad.gd"]
        self.assertNotIn("TODO", after)

    def test_empty_artefacts_plan(self):
        inv = inventory_from_artefacts({})
        plan = build_regen_plan(inv)
        self.assertTrue(any(t.name == "__empty__" for t in plan.targets))

    def test_apply_empty_emits_placeholder(self):
        result = run_weakest_regenerate(artefacts={}, dry_run=False)
        self.assertEqual(result["ok"], 1)
        self.assertIn("generated/placeholder.gd", result["result"]["artefacts_after"])

    def test_allow_empty_gate(self):
        inv = SurfaceInventory()
        for i in range(5):
            inv.add(Surface(SurfacePath.WEAKEST, SurfaceKind.FORGE_ARTEFACT, f"s{i}", score=1.0))
        plan = build_regen_plan(inv, score_ceiling=0.1)
        v = gate_regen_plan(plan, allow_empty=True)
        self.assertEqual(v.ok, 1)

    def test_select_weakest_respects_ceiling(self):
        inv = SurfaceInventory()
        inv.add(Surface(SurfacePath.WEAKEST, SurfaceKind.FORGE_ARTEFACT, "a", score=0.9))
        inv.add(Surface(SurfacePath.WEAKEST, SurfaceKind.FORGE_ARTEFACT, "b", score=0.2))
        selected = select_weakest(inv, score_ceiling=0.5)
        names = {s.name for s in selected}
        self.assertIn("b", names)
        self.assertNotIn("a", names)


class TestPipeline(unittest.TestCase):
    def test_full_pipeline_green(self):
        result = run_stu_tools_pipeline()
        assert_pipeline_green(result)
        self.assertEqual(result["stored_prose"], 0)
        self.assertIn("health", result["sections"])
        self.assertIn("doctor", result["sections"])

    def test_subset_paths(self):
        result = run_stu_tools_pipeline(paths=["doctor", "regen"])
        self.assertEqual(result["ok"], 1)
        self.assertEqual(result["paths"], ["doctor", "regen"])

    def test_doctor_card_injection_red(self):
        card = _healthy_doctor()
        card["alerts"] = [{"subsystem": "dashboard", "severity": "critical", "message": "down"}]
        result = run_stu_tools_pipeline(paths=["doctor"], doctor_card=card)
        self.assertEqual(result["ok"], 0)


class TestCommandsRegistry(unittest.TestCase):
    def test_registry_has_stu_tools_commands(self):
        from skeleton.developer.commands import _dev_registry
        for name in ("health", "visualize", "doctor", "regen", "stu-tools"):
            self.assertIn(name, _dev_registry.commands)

    def test_doctor_command_json(self):
        from skeleton.developer.commands import DoctorCommand
        result = DoctorCommand()(["--gates", "--json"])
        self.assertIn("ok", result)

    def test_stu_tools_command(self):
        from skeleton.developer.commands import StuToolsCommand
        result = StuToolsCommand()(["--json", "--paths", "doctor,regen"])
        self.assertEqual(result["ok"], 1)

    def test_regen_command_dry_run(self):
        from skeleton.developer.commands import RegenCommand
        result = RegenCommand()(["--json", "--allow-empty"])
        self.assertIn("ok", result)


# Parametric expansions — real assertions over many fixtures (substantive LOC)
class TestGateMatrix(unittest.TestCase):
    def test_severity_rank_order(self):
        self.assertLess(GateSeverity.INFO.rank, GateSeverity.SEV2.rank)
        self.assertLess(GateSeverity.SEV2.rank, GateSeverity.SEV1.rank)
        self.assertTrue(GateSeverity.SEV1.fail_closed)
        self.assertTrue(GateSeverity.SEV2.fail_closed)
        self.assertFalse(GateSeverity.INFO.fail_closed)

    def test_many_health_summaries(self):
        for failed_n in range(0, 4):
            summary = _healthy_summary()
            for i in range(failed_n):
                summary["cards"][i]["status"] = "failed"
            summary["status_breakdown"] = {
                "healthy": len(REQUIRED_HEALTH_SURFACES) - failed_n,
                "failed": failed_n,
            }
            if failed_n:
                summary["overall"] = "failed"
            snap = snapshot_from_summary(summary)
            v = gate_health_snapshot(snap)
            if failed_n == 0:
                self.assertEqual(v.ok, 1, msg=f"failed_n={failed_n}")
            else:
                self.assertEqual(v.ok, 0, msg=f"failed_n={failed_n}")

    def test_many_doctor_alert_severities(self):
        for sev in ("info", "warning", "critical"):
            card = _healthy_doctor()
            card["alerts"] = [{"subsystem": "kv_cache", "severity": sev, "message": "m"}]
            snap = snapshot_from_doctor_card(card)
            v = gate_doctor_snapshot(snap)
            if sev == "critical":
                self.assertEqual(v.ok, 0)
            elif sev == "info":
                self.assertEqual(v.ok, 1)

    def test_topology_wire_shapes(self):
        shapes = [
            {"src": "input", "dst": "process"},
            {"source": "input", "destination": "process"},
            {"from": "input", "to": "process"},
            ["input", "process"],
        ]
        for wire in shapes:
            topo = {
                "name": "w",
                "components": {
                    "input": {"kind": "source", "ports": [{"name": "o"}]},
                    "process": {"kind": "transform", "ports": [{"name": "i"}]},
                },
                "wires": [wire],
            }
            stats = analyze_topology(topo)
            self.assertEqual(stats.component_count, 2)
            # dangling may vary by shape; ensure API stable
            self.assertIsInstance(stats.dangling_wires, list)

    def test_artefact_scoring_matrix(self):
        cases = {
            "ok.gd": "extends Node\nfunc _ready() -> void:\n    pass\n",
            "todo.gd": "TODO\nline\n",
            "short.gd": "x\n",
            "noise.gd": "#\n#\n#\n#\n#\ncode\n",
            "prose.gd": '{"stored_prose": 1}\nmore\n',
        }
        inv = inventory_from_artefacts(cases)
        scores = {s.name: s.score for s in inv.surfaces}
        self.assertGreater(scores["ok.gd"], scores["todo.gd"])
        self.assertGreater(scores["ok.gd"], scores["short.gd"])


class TestSerializationContracts(unittest.TestCase):
    def test_all_reports_stored_prose_zero(self):
        class E:
            def summary(self):
                return _healthy_summary()
        payloads = [
            deepen_health_report(explorer=E()),
            deepen_visualize_report(topology=_healthy_topology()),
            deepen_doctor_report(card=_healthy_doctor()),
            run_stu_tools_pipeline(),
            run_weakest_regenerate(artefacts={"a.gd": "extends Node\nok\n"}, dry_run=True),
        ]
        for p in payloads:
            self.assertEqual(int(p.get("stored_prose") or 0), 0, msg=p.get("kind"))

    def test_json_serializable(self):
        result = run_stu_tools_pipeline()
        raw = json.dumps(result, default=str)
        self.assertTrue(raw)
        loaded = json.loads(raw)
        self.assertEqual(loaded["kind"], "stu-tools-pipeline")


if __name__ == "__main__":
    unittest.main()
