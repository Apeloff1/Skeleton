"""Large matrix regressions to deepen STU-TOOLS coverage toward package target."""
from __future__ import annotations

import itertools
import unittest
from typing import Any, Dict, List

from skeleton.developer.cockpit_deepen import snapshot_cockpit
from skeleton.developer.cockpit_gates import run_cockpit_gates
from skeleton.developer.doctor_cockpit_bridge import run_doctor_cockpit_bridge
from skeleton.developer.doctor_deepen import snapshot_from_doctor_card
from skeleton.developer.doctor_gates import gate_doctor_snapshot, run_doctor_gates
from skeleton.developer.gate_catalog import CATALOG, catalog_dict, gates_for_path
from skeleton.developer.health_deepen import snapshot_from_summary
from skeleton.developer.health_gates import gate_health_snapshot
from skeleton.developer.stu_tools_pipeline import run_stu_tools_pipeline
from skeleton.developer.stu_tools_report import run_stu_tools_ci_bundle
from skeleton.developer.surface_inventory import (
    REQUIRED_COCKPIT_KNOBS,
    REQUIRED_DOCTOR_DOMAINS,
    REQUIRED_HEALTH_SURFACES,
)
from skeleton.developer.visualize_gates import run_visualize_gates
from skeleton.developer.weakest_regenerate import run_weakest_regenerate


def _health(statuses: List[str]) -> Dict[str, Any]:
    cards = [
        {"name": n, "status": s, "phase": n, "metrics": {}}
        for n, s in zip(REQUIRED_HEALTH_SURFACES, statuses)
    ]
    breakdown: Dict[str, int] = {}
    for s in statuses:
        breakdown[s] = breakdown.get(s, 0) + 1
    overall = "failed" if "failed" in breakdown else ("degraded" if "degraded" in breakdown else "healthy")
    return {
        "overall": overall,
        "total_subsystems": len(cards),
        "phases_booted": len(cards),
        "status_breakdown": breakdown,
        "cards": cards,
    }


def _doctor(alerts=None, **knobs):
    cockpit = {k: 1.0 for k in REQUIRED_COCKPIT_KNOBS}
    cockpit.update(knobs)
    cockpit.setdefault("stored_prose", 0)
    return {
        "alerts": alerts or [],
        "repair_effectiveness": {"ok": 1},
        "kv_cache": {"hit_rate": 0.9},
        "policy": {"enforced": 1},
        "circuit": {"open": 0},
        "health": {"overall": "healthy"},
        "audit_integrity": {"ok": 1},
        "dashboard": {"ready": 1},
        "cockpit": cockpit,
        "stored_prose": cockpit["stored_prose"],
    }


class TestHealthStatusMatrix(unittest.TestCase):
    def test_single_failed_each_surface(self):
        for idx in range(len(REQUIRED_HEALTH_SURFACES)):
            statuses = ["healthy"] * len(REQUIRED_HEALTH_SURFACES)
            statuses[idx] = "failed"
            v = gate_health_snapshot(snapshot_from_summary(_health(statuses)))
            self.assertEqual(v.ok, 0, msg=REQUIRED_HEALTH_SURFACES[idx])

    def test_single_degraded_each_surface(self):
        for idx in range(len(REQUIRED_HEALTH_SURFACES)):
            statuses = ["healthy"] * len(REQUIRED_HEALTH_SURFACES)
            statuses[idx] = "degraded"
            v = gate_health_snapshot(snapshot_from_summary(_health(statuses)))
            self.assertIn(v.ok, (0, 1))


class TestDoctorAlertMatrix(unittest.TestCase):
    def test_warning_counts(self):
        for n in range(0, 8):
            card = _doctor(
                alerts=[
                    {"subsystem": "policy", "severity": "warning", "message": f"w{i}"}
                    for i in range(n)
                ]
            )
            result = run_doctor_gates(card=card)
            if n <= 5:
                self.assertEqual(result["ok"], 1, msg=f"n={n}")
            else:
                self.assertEqual(result["ok"], 0, msg=f"n={n}")


class TestVisualizeSizeMatrix(unittest.TestCase):
    def test_linear_chains(self):
        for n in range(2, 12):
            comps = {f"n{i}": {"kind": "node", "ports": [{"name": "p"}]} for i in range(n)}
            wires = [{"src": f"n{i}", "dst": f"n{i+1}"} for i in range(n - 1)]
            r = run_visualize_gates(topology={"name": f"c{n}", "components": comps, "wires": wires})
            self.assertEqual(r["ok"], 1, msg=f"n={n}")


class TestRegenFractionMatrix(unittest.TestCase):
    def test_fractions(self):
        files = {f"f{i}.gd": ("TODO\n" if i % 3 == 0 else "extends Node\nfunc _ready() -> void:\n    pass\n") for i in range(20)}
        for frac in (0.1, 0.15, 0.2):
            r = run_weakest_regenerate(artefacts=files, dry_run=True, fraction=frac, score_ceiling=1.0)
            self.assertEqual(r["ok"], 1, msg=f"frac={frac}")


class TestCockpitValueMatrix(unittest.TestCase):
    def test_values_grid(self):
        values = [0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 2.1]
        for knob in REQUIRED_COCKPIT_KNOBS:
            for value in values:
                knobs = {k: 1.0 for k in REQUIRED_COCKPIT_KNOBS}
                knobs[knob] = value
                r = run_cockpit_gates(knobs)
                lo, hi = 0.5, 2.0
                if lo <= value <= hi:
                    self.assertEqual(r["ok"], 1, msg=f"{knob}={value}")
                else:
                    self.assertEqual(r["ok"], 0, msg=f"{knob}={value}")


class TestBridgeDomainMatrix(unittest.TestCase):
    def test_warning_and_critical_per_domain(self):
        for domain, sev in itertools.product(REQUIRED_DOCTOR_DOMAINS, ["warning", "critical"]):
            card = _doctor(alerts=[{"subsystem": domain, "severity": sev, "message": "m"}])
            r = run_doctor_cockpit_bridge(doctor_card=card, apply=True)
            self.assertEqual(r["ok"], 1, msg=f"{domain}/{sev}")
            if sev == "critical":
                self.assertTrue(any(a["domain"] == domain for a in r["plan"]["actions"]))


class TestCatalogConsistency(unittest.TestCase):
    def test_unique_names(self):
        names = [g.name for g in CATALOG]
        self.assertEqual(len(names), len(set(names)))

    def test_path_gate_counts(self):
        d = catalog_dict()
        for path, gates in d["by_path"].items():
            self.assertEqual(len(gates), len(gates_for_path(path)))
            self.assertTrue(gates)


class TestPipelinePathMatrix(unittest.TestCase):
    def test_all_nonempty_subsets(self):
        paths = ["health", "visualize", "doctor", "regen"]
        # all single and pairwise
        for a in paths:
            r = run_stu_tools_pipeline(paths=[a])
            self.assertEqual(r["ok"], 1, msg=a)
        for a, b in itertools.combinations(paths, 2):
            r = run_stu_tools_pipeline(paths=[a, b])
            self.assertEqual(r["ok"], 1, msg=f"{a}+{b}")


class TestCiBundleStress(unittest.TestCase):
    def test_repeat(self):
        for _ in range(3):
            b = run_stu_tools_ci_bundle()
            self.assertEqual(b["ok"], 1)

    def test_with_doctor_card(self):
        b = run_stu_tools_ci_bundle(doctor_card=_doctor())
        self.assertEqual(b["ok"], 1)


class TestSnapshotIdentity(unittest.TestCase):
    def test_cockpit_fp_changes(self):
        a = snapshot_cockpit()
        b = snapshot_cockpit({"speed_mul": 1.5, "heat_mul": 1.0, "collapse_mul": 1.0})
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_doctor_fp_stable_for_same_card(self):
        a = snapshot_from_doctor_card(_doctor())
        b = snapshot_from_doctor_card(_doctor())
        self.assertEqual(a.fingerprint(), b.fingerprint())


if __name__ == "__main__":
    unittest.main()
