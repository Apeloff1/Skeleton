"""Additional STU-TOOLS scenario / property regressions."""
from __future__ import annotations

import unittest
from typing import Any, Dict, List

from skeleton.developer.doctor_deepen import diff_doctor, snapshot_from_doctor_card
from skeleton.developer.doctor_gates import gate_doctor_snapshot, run_doctor_gates
from skeleton.developer.gate_verdict import GateSeverity, GateSuite, collect_verdict, fail_gate, pass_gate
from skeleton.developer.health_deepen import diff_health, snapshot_from_summary
from skeleton.developer.health_gates import gate_health_snapshot, run_health_gates
from skeleton.developer.stu_tools_pipeline import run_stu_tools_pipeline
from skeleton.developer.surface_inventory import (
    REQUIRED_COCKPIT_KNOBS,
    REQUIRED_DOCTOR_DOMAINS,
    REQUIRED_HEALTH_SURFACES,
    Surface,
    SurfaceInventory,
    SurfaceKind,
    SurfacePath,
    inventory_from_artefacts,
    inventory_from_cockpit,
    inventory_from_doctor_card,
    inventory_from_health_summary,
)
from skeleton.developer.visualize_deepen import analyze_topology, snapshot_visualize
from skeleton.developer.visualize_gates import run_visualize_gates
from skeleton.developer.weakest_regenerate import build_regen_plan, run_weakest_regenerate


def healthy_summary() -> Dict[str, Any]:
    return {
        "overall": "healthy",
        "total_subsystems": len(REQUIRED_HEALTH_SURFACES),
        "phases_booted": len(REQUIRED_HEALTH_SURFACES),
        "status_breakdown": {"healthy": len(REQUIRED_HEALTH_SURFACES)},
        "cards": [
            {"name": n, "status": "healthy", "phase": n, "metrics": {"latency_ms": 1}}
            for n in REQUIRED_HEALTH_SURFACES
        ],
    }


def healthy_doctor() -> Dict[str, Any]:
    return {
        "alerts": [],
        "repair_effectiveness": {"ok": 1},
        "kv_cache": {"hit_rate": 0.95},
        "policy": {"enforced": 1},
        "circuit": {"open": 0},
        "health": {"overall": "healthy"},
        "audit_integrity": {"ok": 1},
        "dashboard": {"ready": 1},
        "cockpit": {k: 1.0 for k in REQUIRED_COCKPIT_KNOBS},
        "stored_prose": 0,
    }


class TestHealthScenarioGrid(unittest.TestCase):
    def test_phase_boot_counts(self):
        for phases in range(0, len(REQUIRED_HEALTH_SURFACES) + 1):
            summary = healthy_summary()
            summary["phases_booted"] = phases
            snap = snapshot_from_summary(summary)
            self.assertEqual(snap.phases_booted, phases)
            # gates still evaluate without crash
            v = gate_health_snapshot(snap)
            self.assertIn(v.ok, (0, 1))

    def test_degraded_mean_floor(self):
        summary = healthy_summary()
        for card in summary["cards"]:
            card["status"] = "degraded"
            card["metrics"] = {}
        summary["overall"] = "degraded"
        summary["status_breakdown"] = {"degraded": len(REQUIRED_HEALTH_SURFACES)}
        snap = snapshot_from_summary(summary)
        v = gate_health_snapshot(snap, mean_score_floor=0.99)
        self.assertEqual(v.ok, 0)

    def test_diff_identical_not_regressed(self):
        a = snapshot_from_summary(healthy_summary())
        b = snapshot_from_summary(healthy_summary())
        d = diff_health(a, b)
        self.assertFalse(d.regressed)


class TestDoctorScenarioGrid(unittest.TestCase):
    def test_each_domain_critical(self):
        for domain in REQUIRED_DOCTOR_DOMAINS:
            card = healthy_doctor()
            card["alerts"] = [{"subsystem": domain, "severity": "critical", "message": "x"}]
            snap = snapshot_from_doctor_card(card)
            v = gate_doctor_snapshot(snap)
            self.assertEqual(v.ok, 0, msg=domain)

    def test_warning_threshold(self):
        card = healthy_doctor()
        card["alerts"] = [
            {"subsystem": "policy", "severity": "warning", "message": f"w{i}"}
            for i in range(6)
        ]
        result = run_doctor_gates(card=card)
        self.assertEqual(result["ok"], 0)

    def test_cockpit_each_knob(self):
        for knob in REQUIRED_COCKPIT_KNOBS:
            card = healthy_doctor()
            card["cockpit"][knob] = 0.1
            snap = snapshot_from_doctor_card(card)
            v = gate_doctor_snapshot(snap)
            self.assertEqual(v.ok, 0, msg=knob)

    def test_diff_clearing_critical_not_regressed(self):
        bad = healthy_doctor()
        bad["alerts"] = [{"subsystem": "health", "severity": "critical", "message": "x"}]
        a = snapshot_from_doctor_card(bad)
        b = snapshot_from_doctor_card(healthy_doctor())
        d = diff_doctor(a, b)
        self.assertFalse(d.regressed)


class TestVisualizeScenarioGrid(unittest.TestCase):
    def test_chain_lengths(self):
        for n in range(2, 8):
            comps = {f"n{i}": {"kind": "node", "ports": [{"name": "p"}]} for i in range(n)}
            wires = [{"src": f"n{i}", "dst": f"n{i+1}"} for i in range(n - 1)]
            topo = {"name": f"c{n}", "components": comps, "wires": wires}
            stats = analyze_topology(topo)
            self.assertEqual(stats.component_count, n)
            result = run_visualize_gates(topology=topo)
            self.assertEqual(result["ok"], 1, msg=f"n={n}")

    def test_all_orphans(self):
        topo = {
            "name": "orph",
            "components": {f"o{i}": {"kind": "x", "ports": []} for i in range(5)},
            "wires": [],
        }
        result = run_visualize_gates(topology=topo, max_orphans=1)
        self.assertEqual(result["ok"], 0)


class TestRegenScenarioGrid(unittest.TestCase):
    def test_batch_artefacts(self):
        files = {f"f{i}.gd": ("TODO\n" if i % 2 else "extends Node\nfunc _ready() -> void:\n    pass\n") for i in range(12)}
        result = run_weakest_regenerate(
            artefacts=files,
            dry_run=False,
            fraction=0.2,
            score_ceiling=1.0,
        )
        self.assertEqual(result["ok"], 1)
        after = result["result"]["artefacts_after"]
        applied = set(result["result"]["applied"])
        self.assertTrue(applied)
        for name in applied:
            self.assertNotIn("TODO", after[name])

    def test_plan_fingerprint_changes(self):
        a = build_regen_plan(inventory_from_artefacts({"a.gd": "TODO\n"}))
        b = build_regen_plan(inventory_from_artefacts({"a.gd": "extends Node\nok\nok\n"}))
        self.assertNotEqual(a.fingerprint(), b.fingerprint())


class TestPipelineStress(unittest.TestCase):
    def test_repeated_pipeline(self):
        for _ in range(5):
            r = run_stu_tools_pipeline()
            self.assertEqual(r["ok"], 1)

    def test_path_permutations(self):
        paths = ["health", "visualize", "doctor", "regen"]
        for i in range(len(paths)):
            subset = paths[: i + 1]
            r = run_stu_tools_pipeline(paths=subset)
            self.assertEqual(r["ok"], 1, msg=str(subset))


class TestInventoryFuzzLite(unittest.TestCase):
    def test_many_surfaces_mean(self):
        inv = SurfaceInventory()
        for i in range(100):
            inv.add(
                Surface(
                    SurfacePath.HEALTH,
                    SurfaceKind.SUBSYSTEM,
                    f"s{i}",
                    score=(i % 10) / 10,
                    status="healthy" if i % 10 > 3 else "degraded",
                )
            )
        self.assertEqual(len(inv.surfaces), 100)
        self.assertGreaterEqual(len(inv.weakest(fraction=0.15)), 1)
        self.assertTrue(0.0 <= inv.mean_score() <= 1.0)

    def test_cockpit_prose_law(self):
        inv = inventory_from_cockpit({**{k: 1.0 for k in REQUIRED_COCKPIT_KNOBS}, "stored_prose": 3})
        self.assertEqual(inv.stored_prose, 3)
        prose = [s for s in inv.surfaces if s.name == "stored_prose"][0]
        self.assertEqual(prose.score, 0.0)


class TestFailClosedContracts(unittest.TestCase):
    def test_collector_crash_health(self):
        class Boom:
            def summary(self):
                raise RuntimeError("boom")
        r = run_health_gates(explorer=Boom())
        self.assertEqual(r["ok"], 0)
        self.assertIn("health.collect", r["banner"])

    def test_suite_blocks_list(self):
        v = collect_verdict(
            "x",
            [
                pass_gate("a"),
                fail_gate("b", reason="x", severity=GateSeverity.SEV1),
                fail_gate("c", reason="y", severity=GateSeverity.INFO),
            ],
        )
        self.assertEqual([g.name for g in v.blocking], ["b"])


if __name__ == "__main__":
    unittest.main()
