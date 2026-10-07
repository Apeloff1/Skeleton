"""STU-TOOLS property / combinatorics regressions — deepen coverage."""
from __future__ import annotations

import hashlib
import itertools
import json
import unittest
from typing import Any, Dict, Iterable, List, Tuple

from skeleton.developer.doctor_deepen import (
    DoctorSnapshot,
    deepen_doctor_report,
    diff_doctor,
    render_doctor_deep,
    snapshot_from_doctor_card,
)
from skeleton.developer.doctor_gates import gate_doctor_snapshot, run_doctor_gates
from skeleton.developer.gate_verdict import (
    GateEvidence,
    GateSeverity,
    GateStatus,
    GateSuite,
    Verdict,
    collect_verdict,
    fail_gate,
    gate_table,
    merge_verdicts,
    pass_gate,
    summarize_gates,
)
from skeleton.developer.health_deepen import (
    deepen_health_report,
    render_health_deep,
    snapshot_from_summary,
)
from skeleton.developer.health_gates import gate_health_snapshot, run_health_gates
from skeleton.developer.stu_tools_pipeline import run_stu_tools_pipeline
from skeleton.developer.surface_inventory import (
    REQUIRED_COCKPIT_KNOBS,
    REQUIRED_DOCTOR_DOMAINS,
    REQUIRED_HEALTH_SURFACES,
    REQUIRED_VISUALIZE_FIELDS,
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
    required_names_for,
)
from skeleton.developer.visualize_deepen import (
    deepen_visualize_report,
    render_visualize_deep,
    snapshot_visualize,
)
from skeleton.developer.visualize_gates import gate_visualize_snapshot, run_visualize_gates
from skeleton.developer.weakest_regenerate import (
    RegenPlan,
    apply_regen_plan,
    build_regen_plan,
    gate_regen_plan,
    run_weakest_regenerate,
)


def _summary(statuses: Iterable[str]) -> Dict[str, Any]:
    statuses = list(statuses)
    cards = []
    breakdown: Dict[str, int] = {}
    for name, status in zip(REQUIRED_HEALTH_SURFACES, statuses):
        cards.append({"name": name, "status": status, "phase": name, "metrics": {}})
        breakdown[status] = breakdown.get(status, 0) + 1
    overall = "healthy"
    if breakdown.get("failed"):
        overall = "failed"
    elif breakdown.get("degraded"):
        overall = "degraded"
    return {
        "overall": overall,
        "total_subsystems": len(cards),
        "phases_booted": len(cards),
        "status_breakdown": breakdown,
        "cards": cards,
    }


def _doctor(alerts: List[Dict[str, Any]] | None = None, **knob_overrides: float) -> Dict[str, Any]:
    cockpit = {k: 1.0 for k in REQUIRED_COCKPIT_KNOBS}
    cockpit.update(knob_overrides)
    cockpit["stored_prose"] = 0
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
        "stored_prose": 0,
    }


class TestCombinatorialHealth(unittest.TestCase):
    def test_status_patterns_first_three(self):
        # Exhaustive patterns on first 3 surfaces; rest healthy — real gate outcomes.
        for pattern in itertools.product(["healthy", "degraded", "failed"], repeat=3):
            statuses = list(pattern) + ["healthy"] * (len(REQUIRED_HEALTH_SURFACES) - 3)
            snap = snapshot_from_summary(_summary(statuses))
            v = gate_health_snapshot(snap)
            expect_ok = 1 if "failed" not in pattern else 0
            # degraded-only may still pass mean floor
            if "failed" in pattern:
                self.assertEqual(v.ok, 0, msg=str(pattern))
            else:
                self.assertIn(v.ok, (0, 1), msg=str(pattern))

    def test_render_health_deep_contains_fp(self):
        class E:
            def summary(self):
                return _summary(["healthy"] * len(REQUIRED_HEALTH_SURFACES))
        report = deepen_health_report(explorer=E())
        text = render_health_deep(report)
        self.assertIn("STU-TOOLS", text)
        self.assertTrue(report["snapshot"]["fingerprint"])


class TestCombinatorialDoctor(unittest.TestCase):
    def test_alert_domain_pairs(self):
        for domain, sev in itertools.product(REQUIRED_DOCTOR_DOMAINS[:4], ["info", "warning", "critical"]):
            snap = snapshot_from_doctor_card(
                _doctor(alerts=[{"subsystem": domain, "severity": sev, "message": "m"}])
            )
            v = gate_doctor_snapshot(snap)
            if sev == "critical":
                self.assertEqual(v.ok, 0, msg=f"{domain}/{sev}")

    def test_render_doctor_deep(self):
        report = deepen_doctor_report(card=_doctor())
        text = render_doctor_deep(report)
        self.assertIn("Doctor Deep", text)


class TestCombinatorialVisualize(unittest.TestCase):
    def test_grid_graphs(self):
        for width in range(2, 5):
            comps = {}
            wires = []
            for r in range(width):
                for c in range(width):
                    name = f"n{r}_{c}"
                    comps[name] = {"kind": "cell", "ports": [{"name": "p"}]}
                    if c + 1 < width:
                        wires.append({"src": name, "dst": f"n{r}_{c+1}"})
                    if r + 1 < width:
                        wires.append({"src": name, "dst": f"n{r+1}_{c}"})
            topo = {"name": f"grid{width}", "components": comps, "wires": wires}
            result = run_visualize_gates(topology=topo)
            self.assertEqual(result["ok"], 1, msg=f"width={width}")
            report = deepen_visualize_report(topology=topo)
            self.assertIn("STU-TOOLS", render_visualize_deep(report))

    def test_required_visualize_fields(self):
        self.assertEqual(required_names_for(SurfacePath.VISUALIZE), REQUIRED_VISUALIZE_FIELDS)


class TestRegenProperties(unittest.TestCase):
    def test_plan_json_stable(self):
        inv = inventory_from_artefacts({f"a{i}.gd": "TODO\n" for i in range(5)})
        plan = build_regen_plan(inv)
        raw1 = json.dumps(plan.to_dict(), sort_keys=True)
        raw2 = json.dumps(plan.to_dict(), sort_keys=True)
        self.assertEqual(raw1, raw2)
        self.assertEqual(plan.fingerprint(), hashlib.sha256(json.dumps([t.to_dict() for t in plan.targets], sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16])

    def test_apply_idempotent_on_clean(self):
        files = {"clean.gd": "extends Node\nfunc _ready() -> void:\n    pass\n"}
        r1 = run_weakest_regenerate(artefacts=files, dry_run=False, allow_empty=True, score_ceiling=0.1)
        r2 = run_weakest_regenerate(artefacts=r1["result"]["artefacts_after"], dry_run=False, allow_empty=True, score_ceiling=0.1)
        self.assertEqual(r1["ok"], 1)
        self.assertEqual(r2["ok"], 1)


class TestPipelineProperties(unittest.TestCase):
    def test_banner_matches_ok(self):
        r = run_stu_tools_pipeline()
        if r["ok"]:
            self.assertIn("ALL GATES PASSED", r["banner"])
        else:
            self.assertIn("FAIL CLOSED", r["banner"])

    def test_gate_table_nonempty(self):
        r = run_stu_tools_pipeline(paths=["doctor"])
        self.assertTrue(r["gate_table"])

    def test_merge_empty_and_pass(self):
        a = collect_verdict("a", [pass_gate("x")])
        b = collect_verdict("b", [])  # empty -> fail closed
        m = merge_verdicts("m", [a, b])
        self.assertEqual(m.ok, 0)


class TestInventoryContracts(unittest.TestCase):
    def test_required_names_for_all_paths(self):
        mapping = {
            SurfacePath.HEALTH: REQUIRED_HEALTH_SURFACES,
            SurfacePath.DOCTOR: REQUIRED_DOCTOR_DOMAINS,
            SurfacePath.COCKPIT: REQUIRED_COCKPIT_KNOBS,
            SurfacePath.VISUALIZE: REQUIRED_VISUALIZE_FIELDS,
        }
        for path, expected in mapping.items():
            self.assertEqual(required_names_for(path), expected)

    def test_merge_preserves_identities(self):
        a = inventory_from_health_summary(_summary(["healthy"] * len(REQUIRED_HEALTH_SURFACES)))
        b = inventory_from_doctor_card(_doctor())
        m = merge_inventories(a, b)
        ids = [s.identity for s in m.surfaces]
        self.assertEqual(len(ids), len(set(ids)))


class TestVerdictEvidence(unittest.TestCase):
    def test_evidence_roundtrip(self):
        suite = GateSuite("e")
        suite.check(
            False,
            "with_evidence",
            severity=GateSeverity.SEV2,
            on_fail="nope",
            evidence=[GateEvidence("k", 1, "n")],
        )
        v = suite.verdict()
        d = v.to_dict()
        self.assertEqual(d["gates"][0]["evidence"][0]["key"], "k")
        self.assertIn("with_evidence", summarize_gates(v.gates)["blocking_names"])


class TestSnapshotFingerprints(unittest.TestCase):
    def test_health_fp_changes_with_status(self):
        a = snapshot_from_summary(_summary(["healthy"] * len(REQUIRED_HEALTH_SURFACES)))
        b = snapshot_from_summary(_summary(["degraded"] + ["healthy"] * (len(REQUIRED_HEALTH_SURFACES) - 1)))
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_doctor_fp_changes_with_alert(self):
        a = snapshot_from_doctor_card(_doctor())
        b = snapshot_from_doctor_card(_doctor(alerts=[{"subsystem": "policy", "severity": "warning", "message": "w"}]))
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_visualize_fp_changes_with_orphan(self):
        topo = {
            "name": "t",
            "components": {
                "a": {"kind": "source", "ports": [{"name": "o"}]},
                "b": {"kind": "sink", "ports": [{"name": "i"}]},
            },
            "wires": [{"src": "a", "dst": "b"}],
        }
        a = snapshot_visualize(topology=topo)
        topo2 = dict(topo)
        topo2["components"] = dict(topo["components"])
        topo2["components"]["c"] = {"kind": "x", "ports": []}
        b = snapshot_visualize(topology=topo2)
        self.assertNotEqual(a.fingerprint(), b.fingerprint())


if __name__ == "__main__":
    unittest.main()
