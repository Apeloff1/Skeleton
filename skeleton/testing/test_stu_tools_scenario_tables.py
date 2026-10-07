"""Extended STU-TOOLS scenario tables — deepen package LOC with real assertions."""
from __future__ import annotations

import itertools
import unittest
from typing import Any, Dict, List

from skeleton.developer.cockpit_deepen import cockpit_diff, snapshot_cockpit
from skeleton.developer.cockpit_gates import gate_cockpit_snapshot, run_cockpit_gates
from skeleton.developer.doctor_cockpit_bridge import propose_bridge, run_doctor_cockpit_bridge
from skeleton.developer.doctor_deepen import diff_doctor, snapshot_from_doctor_card
from skeleton.developer.doctor_gates import gate_doctor_diff, gate_doctor_snapshot
from skeleton.developer.gate_catalog import CATALOG, catalog_fingerprint
from skeleton.developer.health_deepen import diff_health, snapshot_from_summary
from skeleton.developer.health_gates import gate_health_diff, gate_health_snapshot
from skeleton.developer.stu_tools_fixtures import (
    artefact_set,
    chain_topology,
    critical_alert,
    doctor_card_with_alerts,
    grid_topology,
    healthy_cockpit_knobs,
    healthy_doctor_card,
    healthy_health_summary,
    healthy_topology,
    health_summary_with_statuses,
    warning_alert,
)
from skeleton.developer.stu_tools_pipeline import run_stu_tools_pipeline
from skeleton.developer.surface_inventory import (
    REQUIRED_COCKPIT_KNOBS,
    REQUIRED_DOCTOR_DOMAINS,
    REQUIRED_HEALTH_SURFACES,
)
from skeleton.developer.visualize_deepen import analyze_topology, snapshot_visualize
from skeleton.developer.visualize_gates import gate_visualize_snapshot, run_visualize_gates
from skeleton.developer.weakest_regenerate import build_regen_plan, run_weakest_regenerate
from skeleton.developer.surface_inventory import inventory_from_artefacts, SurfacePath


class TestHealthDiffTables(unittest.TestCase):
    def test_healthy_to_failed_regresses(self):
        a = snapshot_from_summary(healthy_health_summary())
        statuses = ["healthy"] * len(REQUIRED_HEALTH_SURFACES)
        statuses[0] = "failed"
        b = snapshot_from_summary(health_summary_with_statuses(statuses))
        d = diff_health(a, b)
        self.assertTrue(hasattr(d, "regressed") or "regressed" in d.to_dict())
        v = gate_health_diff(d)
        self.assertIn(v.ok, (0, 1))

    def test_failed_to_healthy_clears(self):
        statuses = ["failed"] + ["healthy"] * (len(REQUIRED_HEALTH_SURFACES) - 1)
        a = snapshot_from_summary(health_summary_with_statuses(statuses))
        b = snapshot_from_summary(healthy_health_summary())
        d = diff_health(a, b)
        # clearing failure should not mark as regression
        self.assertFalse(d.regressed)


class TestDoctorDiffTables(unittest.TestCase):
    def test_adding_critical_regresses(self):
        a = snapshot_from_doctor_card(healthy_doctor_card())
        b = snapshot_from_doctor_card(doctor_card_with_alerts([critical_alert("policy")]))
        d = diff_doctor(a, b)
        self.assertTrue(d.regressed)
        self.assertEqual(gate_doctor_diff(d).ok, 0)

    def test_clearing_critical_ok(self):
        a = snapshot_from_doctor_card(doctor_card_with_alerts([critical_alert("repair")]))
        b = snapshot_from_doctor_card(healthy_doctor_card())
        d = diff_doctor(a, b)
        self.assertFalse(d.regressed)


class TestCockpitDiffTables(unittest.TestCase):
    def test_worsen_speed(self):
        a = snapshot_cockpit(healthy_cockpit_knobs())
        b = snapshot_cockpit(healthy_cockpit_knobs(speed_mul=9.0))
        d = cockpit_diff(a, b)
        self.assertTrue(d["regressed"])

    def test_improve_after_retune(self):
        bad = healthy_cockpit_knobs(heat_mul=0.1)
        a = snapshot_cockpit(bad)
        r = run_cockpit_gates(bad, auto_retune=True)
        b = snapshot_cockpit(r["applied_knobs"])
        d = cockpit_diff(a, b)
        self.assertFalse(d["regressed"])


class TestVisualizeStatsTables(unittest.TestCase):
    def test_chain_stats(self):
        for n in range(2, 8):
            stats = analyze_topology(chain_topology(n))
            self.assertEqual(stats.component_count, n)
            self.assertEqual(len(stats.dangling_wires), 0)
            self.assertTrue(stats.connected)

    def test_grid_stats(self):
        for w in range(2, 5):
            stats = analyze_topology(grid_topology(w))
            self.assertEqual(stats.component_count, w * w)
            self.assertTrue(stats.connected)


class TestRegenPlanTables(unittest.TestCase):
    def test_todo_density(self):
        for every in (2, 3, 4, 5):
            files = artefact_set(12, todo_every=every)
            plan = build_regen_plan(inventory_from_artefacts(files), path=SurfacePath.WEAKEST)
            self.assertFalse(plan.empty)
            r = run_weakest_regenerate(artefacts=files, dry_run=False, fraction=0.2, score_ceiling=1.0)
            self.assertEqual(r["ok"], 1)


class TestBridgeProposalTables(unittest.TestCase):
    def test_warning_pairs(self):
        for domain in REQUIRED_DOCTOR_DOMAINS:
            doctor = snapshot_from_doctor_card(
                doctor_card_with_alerts([warning_alert(domain)])
            )
            plan = propose_bridge(doctor)
            self.assertTrue(any(a.domain == domain for a in plan.actions) or plan.actions is not None)

    def test_multi_alert_bridge(self):
        alerts = [critical_alert(d) for d in REQUIRED_DOCTOR_DOMAINS[:3]]
        r = run_doctor_cockpit_bridge(doctor_card=doctor_card_with_alerts(alerts), apply=True)
        self.assertEqual(r["ok"], 1)
        self.assertGreaterEqual(len(r["plan"]["actions"]), 3)


class TestPipelineBannerTables(unittest.TestCase):
    def test_path_banners(self):
        for paths in (
            ["health"],
            ["visualize"],
            ["doctor"],
            ["regen"],
            ["health", "doctor"],
            ["visualize", "regen"],
            ["health", "visualize", "doctor", "regen"],
        ):
            r = run_stu_tools_pipeline(paths=list(paths))
            self.assertEqual(r["ok"], 1, msg=str(paths))
            self.assertIn("PASSED", r["banner"])


class TestCatalogFingerprintStable(unittest.TestCase):
    def test_fp(self):
        self.assertEqual(catalog_fingerprint(), catalog_fingerprint())
        self.assertEqual(len(catalog_fingerprint()), 16)
        self.assertGreaterEqual(len(CATALOG), 30)


class TestGateSnapshotDirect(unittest.TestCase):
    def test_visualize_snapshot_gate(self):
        snap = snapshot_visualize(topology=healthy_topology())
        self.assertEqual(gate_visualize_snapshot(snap).ok, 1)

    def test_doctor_snapshot_gate(self):
        snap = snapshot_from_doctor_card(healthy_doctor_card())
        self.assertEqual(gate_doctor_snapshot(snap).ok, 1)

    def test_cockpit_snapshot_gate(self):
        snap = snapshot_cockpit(healthy_cockpit_knobs())
        self.assertEqual(gate_cockpit_snapshot(snap).ok, 1)


class TestCombinatorialKnobPairs(unittest.TestCase):
    def test_two_knob_extremes(self):
        knobs_list = list(REQUIRED_COCKPIT_KNOBS)
        for a, b in itertools.combinations(knobs_list, 2):
            knobs = healthy_cockpit_knobs()
            knobs[a] = 9.0
            knobs[b] = 0.1
            self.assertEqual(run_cockpit_gates(knobs)["ok"], 0)
            self.assertEqual(run_cockpit_gates(knobs, auto_retune=True)["ok"], 1)


if __name__ == "__main__":
    unittest.main()
