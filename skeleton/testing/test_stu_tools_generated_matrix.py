"""Auto-expanded STU-TOOLS gate matrix — one assertion family per case."""
from __future__ import annotations
import unittest
from skeleton.developer.cockpit_gates import run_cockpit_gates
from skeleton.developer.doctor_gates import run_doctor_gates
from skeleton.developer.health_deepen import snapshot_from_summary
from skeleton.developer.health_gates import gate_health_snapshot
from skeleton.developer.stu_tools_fixtures import (
    artefact_set, chain_topology, critical_alert, doctor_card_with_alerts,
    healthy_cockpit_knobs, healthy_doctor_card, healthy_health_summary,
    health_summary_with_statuses, warning_alert,
)
from skeleton.developer.surface_inventory import REQUIRED_COCKPIT_KNOBS, REQUIRED_DOCTOR_DOMAINS, REQUIRED_HEALTH_SURFACES
from skeleton.developer.visualize_gates import run_visualize_gates
from skeleton.developer.weakest_regenerate import run_weakest_regenerate
from skeleton.developer.doctor_cockpit_bridge import run_doctor_cockpit_bridge
from skeleton.developer.path_runners import run_all_paths


class TestGeneratedHealthFailures(unittest.TestCase):
    def test_failed_kernel(self):
        statuses = ["healthy"] * len(REQUIRED_HEALTH_SURFACES)
        statuses[0] = "failed"
        v = gate_health_snapshot(snapshot_from_summary(health_summary_with_statuses(statuses)))
        self.assertEqual(v.ok, 0)

    def test_failed_memory(self):
        statuses = ["healthy"] * len(REQUIRED_HEALTH_SURFACES)
        statuses[1] = "failed"
        v = gate_health_snapshot(snapshot_from_summary(health_summary_with_statuses(statuses)))
        self.assertEqual(v.ok, 0)

    def test_failed_intelligence(self):
        statuses = ["healthy"] * len(REQUIRED_HEALTH_SURFACES)
        statuses[2] = "failed"
        v = gate_health_snapshot(snapshot_from_summary(health_summary_with_statuses(statuses)))
        self.assertEqual(v.ok, 0)

    def test_failed_swarm(self):
        statuses = ["healthy"] * len(REQUIRED_HEALTH_SURFACES)
        statuses[3] = "failed"
        v = gate_health_snapshot(snapshot_from_summary(health_summary_with_statuses(statuses)))
        self.assertEqual(v.ok, 0)

    def test_failed_resilience(self):
        statuses = ["healthy"] * len(REQUIRED_HEALTH_SURFACES)
        statuses[4] = "failed"
        v = gate_health_snapshot(snapshot_from_summary(health_summary_with_statuses(statuses)))
        self.assertEqual(v.ok, 0)

    def test_failed_observability(self):
        statuses = ["healthy"] * len(REQUIRED_HEALTH_SURFACES)
        statuses[5] = "failed"
        v = gate_health_snapshot(snapshot_from_summary(health_summary_with_statuses(statuses)))
        self.assertEqual(v.ok, 0)

    def test_failed_cortex(self):
        statuses = ["healthy"] * len(REQUIRED_HEALTH_SURFACES)
        statuses[6] = "failed"
        v = gate_health_snapshot(snapshot_from_summary(health_summary_with_statuses(statuses)))
        self.assertEqual(v.ok, 0)


class TestGeneratedDoctorCriticals(unittest.TestCase):
    def test_critical_repair(self):
        card = doctor_card_with_alerts([critical_alert("repair")])
        self.assertEqual(run_doctor_gates(card=card)["ok"], 0)
        self.assertEqual(run_doctor_cockpit_bridge(doctor_card=card, apply=True)["ok"], 1)

    def test_critical_kv_cache(self):
        card = doctor_card_with_alerts([critical_alert("kv_cache")])
        self.assertEqual(run_doctor_gates(card=card)["ok"], 0)
        self.assertEqual(run_doctor_cockpit_bridge(doctor_card=card, apply=True)["ok"], 1)

    def test_critical_policy(self):
        card = doctor_card_with_alerts([critical_alert("policy")])
        self.assertEqual(run_doctor_gates(card=card)["ok"], 0)
        self.assertEqual(run_doctor_cockpit_bridge(doctor_card=card, apply=True)["ok"], 1)

    def test_critical_resilience(self):
        card = doctor_card_with_alerts([critical_alert("resilience")])
        self.assertEqual(run_doctor_gates(card=card)["ok"], 0)
        self.assertEqual(run_doctor_cockpit_bridge(doctor_card=card, apply=True)["ok"], 1)

    def test_critical_health(self):
        card = doctor_card_with_alerts([critical_alert("health")])
        self.assertEqual(run_doctor_gates(card=card)["ok"], 0)
        self.assertEqual(run_doctor_cockpit_bridge(doctor_card=card, apply=True)["ok"], 1)

    def test_critical_audit(self):
        card = doctor_card_with_alerts([critical_alert("audit")])
        self.assertEqual(run_doctor_gates(card=card)["ok"], 0)
        self.assertEqual(run_doctor_cockpit_bridge(doctor_card=card, apply=True)["ok"], 1)

    def test_critical_dashboard(self):
        card = doctor_card_with_alerts([critical_alert("dashboard")])
        self.assertEqual(run_doctor_gates(card=card)["ok"], 0)
        self.assertEqual(run_doctor_cockpit_bridge(doctor_card=card, apply=True)["ok"], 1)


class TestGeneratedCockpitOOR(unittest.TestCase):
    def test_speed_mul_low(self):
        knobs = healthy_cockpit_knobs(speed_mul=0.1)
        self.assertEqual(run_cockpit_gates(knobs)["ok"], 0)
        self.assertEqual(run_cockpit_gates(knobs, auto_retune=True)["ok"], 1)

    def test_speed_mul_high(self):
        knobs = healthy_cockpit_knobs(speed_mul=9.0)
        self.assertEqual(run_cockpit_gates(knobs)["ok"], 0)
        self.assertEqual(run_cockpit_gates(knobs, auto_retune=True)["ok"], 1)

    def test_heat_mul_low(self):
        knobs = healthy_cockpit_knobs(heat_mul=0.1)
        self.assertEqual(run_cockpit_gates(knobs)["ok"], 0)
        self.assertEqual(run_cockpit_gates(knobs, auto_retune=True)["ok"], 1)

    def test_heat_mul_high(self):
        knobs = healthy_cockpit_knobs(heat_mul=9.0)
        self.assertEqual(run_cockpit_gates(knobs)["ok"], 0)
        self.assertEqual(run_cockpit_gates(knobs, auto_retune=True)["ok"], 1)

    def test_collapse_mul_low(self):
        knobs = healthy_cockpit_knobs(collapse_mul=0.1)
        self.assertEqual(run_cockpit_gates(knobs)["ok"], 0)
        self.assertEqual(run_cockpit_gates(knobs, auto_retune=True)["ok"], 1)

    def test_collapse_mul_high(self):
        knobs = healthy_cockpit_knobs(collapse_mul=9.0)
        self.assertEqual(run_cockpit_gates(knobs)["ok"], 0)
        self.assertEqual(run_cockpit_gates(knobs, auto_retune=True)["ok"], 1)


class TestGeneratedChains(unittest.TestCase):
    def test_chain_2(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(2))["ok"], 1)

    def test_chain_3(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(3))["ok"], 1)

    def test_chain_4(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(4))["ok"], 1)

    def test_chain_5(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(5))["ok"], 1)

    def test_chain_6(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(6))["ok"], 1)

    def test_chain_7(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(7))["ok"], 1)

    def test_chain_8(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(8))["ok"], 1)

    def test_chain_9(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(9))["ok"], 1)

    def test_chain_10(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(10))["ok"], 1)

    def test_chain_11(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(11))["ok"], 1)

    def test_chain_12(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(12))["ok"], 1)

    def test_chain_13(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(13))["ok"], 1)

    def test_chain_14(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(14))["ok"], 1)

    def test_chain_15(self):
        self.assertEqual(run_visualize_gates(topology=chain_topology(15))["ok"], 1)


class TestGeneratedRegenSizes(unittest.TestCase):
    def test_regen_n4(self):
        files = artefact_set(4, todo_every=2)
        self.assertEqual(run_weakest_regenerate(artefacts=files, dry_run=False, fraction=0.2, score_ceiling=1.0)["ok"], 1)

    def test_regen_n6(self):
        files = artefact_set(6, todo_every=2)
        self.assertEqual(run_weakest_regenerate(artefacts=files, dry_run=False, fraction=0.2, score_ceiling=1.0)["ok"], 1)

    def test_regen_n8(self):
        files = artefact_set(8, todo_every=2)
        self.assertEqual(run_weakest_regenerate(artefacts=files, dry_run=False, fraction=0.2, score_ceiling=1.0)["ok"], 1)

    def test_regen_n10(self):
        files = artefact_set(10, todo_every=2)
        self.assertEqual(run_weakest_regenerate(artefacts=files, dry_run=False, fraction=0.2, score_ceiling=1.0)["ok"], 1)

    def test_regen_n12(self):
        files = artefact_set(12, todo_every=2)
        self.assertEqual(run_weakest_regenerate(artefacts=files, dry_run=False, fraction=0.2, score_ceiling=1.0)["ok"], 1)

    def test_regen_n14(self):
        files = artefact_set(14, todo_every=2)
        self.assertEqual(run_weakest_regenerate(artefacts=files, dry_run=False, fraction=0.2, score_ceiling=1.0)["ok"], 1)

    def test_regen_n16(self):
        files = artefact_set(16, todo_every=2)
        self.assertEqual(run_weakest_regenerate(artefacts=files, dry_run=False, fraction=0.2, score_ceiling=1.0)["ok"], 1)

    def test_regen_n18(self):
        files = artefact_set(18, todo_every=2)
        self.assertEqual(run_weakest_regenerate(artefacts=files, dry_run=False, fraction=0.2, score_ceiling=1.0)["ok"], 1)

    def test_regen_n20(self):
        files = artefact_set(20, todo_every=2)
        self.assertEqual(run_weakest_regenerate(artefacts=files, dry_run=False, fraction=0.2, score_ceiling=1.0)["ok"], 1)

    def test_regen_n22(self):
        files = artefact_set(22, todo_every=2)
        self.assertEqual(run_weakest_regenerate(artefacts=files, dry_run=False, fraction=0.2, score_ceiling=1.0)["ok"], 1)

    def test_regen_n24(self):
        files = artefact_set(24, todo_every=2)
        self.assertEqual(run_weakest_regenerate(artefacts=files, dry_run=False, fraction=0.2, score_ceiling=1.0)["ok"], 1)


class TestGeneratedWarningCounts(unittest.TestCase):
    def test_warnings_0(self):
        alerts = [warning_alert("policy", f"w{i}") for i in range(0)]
        card = doctor_card_with_alerts(alerts)
        expect = 1 if 0 <= 5 else 0
        self.assertEqual(run_doctor_gates(card=card)["ok"], expect)

    def test_warnings_1(self):
        alerts = [warning_alert("policy", f"w{i}") for i in range(1)]
        card = doctor_card_with_alerts(alerts)
        expect = 1 if 1 <= 5 else 0
        self.assertEqual(run_doctor_gates(card=card)["ok"], expect)

    def test_warnings_2(self):
        alerts = [warning_alert("policy", f"w{i}") for i in range(2)]
        card = doctor_card_with_alerts(alerts)
        expect = 1 if 2 <= 5 else 0
        self.assertEqual(run_doctor_gates(card=card)["ok"], expect)

    def test_warnings_3(self):
        alerts = [warning_alert("policy", f"w{i}") for i in range(3)]
        card = doctor_card_with_alerts(alerts)
        expect = 1 if 3 <= 5 else 0
        self.assertEqual(run_doctor_gates(card=card)["ok"], expect)

    def test_warnings_4(self):
        alerts = [warning_alert("policy", f"w{i}") for i in range(4)]
        card = doctor_card_with_alerts(alerts)
        expect = 1 if 4 <= 5 else 0
        self.assertEqual(run_doctor_gates(card=card)["ok"], expect)

    def test_warnings_5(self):
        alerts = [warning_alert("policy", f"w{i}") for i in range(5)]
        card = doctor_card_with_alerts(alerts)
        expect = 1 if 5 <= 5 else 0
        self.assertEqual(run_doctor_gates(card=card)["ok"], expect)

    def test_warnings_6(self):
        alerts = [warning_alert("policy", f"w{i}") for i in range(6)]
        card = doctor_card_with_alerts(alerts)
        expect = 1 if 6 <= 5 else 0
        self.assertEqual(run_doctor_gates(card=card)["ok"], expect)

    def test_warnings_7(self):
        alerts = [warning_alert("policy", f"w{i}") for i in range(7)]
        card = doctor_card_with_alerts(alerts)
        expect = 1 if 7 <= 5 else 0
        self.assertEqual(run_doctor_gates(card=card)["ok"], expect)


class TestGeneratedAllPathsSmoke(unittest.TestCase):
    def test_all_paths_healthy(self):
        self.assertEqual(run_all_paths(doctor_card=healthy_doctor_card())["ok"], 1)


if __name__ == "__main__":
    unittest.main()
