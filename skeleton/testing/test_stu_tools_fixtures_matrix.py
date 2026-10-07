"""Fixture-driven STU-TOOLS deepen matrices."""
from __future__ import annotations

import unittest

from skeleton.developer.cockpit_gates import run_cockpit_gates
from skeleton.developer.doctor_cockpit_bridge import run_doctor_cockpit_bridge
from skeleton.developer.doctor_gates import run_doctor_gates
from skeleton.developer.health_deepen import snapshot_from_summary
from skeleton.developer.health_gates import gate_health_snapshot
from skeleton.developer.path_runners import run_all_paths
from skeleton.developer.stu_tools_fixtures import (
    all_domain_critical_cards,
    all_knob_oor_sets,
    artefact_set,
    chain_topology,
    doctor_card_with_alerts,
    grid_topology,
    healthy_cockpit_knobs,
    healthy_doctor_card,
    healthy_health_summary,
    healthy_topology,
    health_summary_with_statuses,
    warning_alert,
)
from skeleton.developer.stu_tools_report import run_stu_tools_ci_bundle
from skeleton.developer.surface_inventory import REQUIRED_DOCTOR_DOMAINS, REQUIRED_HEALTH_SURFACES
from skeleton.developer.visualize_gates import run_visualize_gates
from skeleton.developer.weakest_regenerate import run_weakest_regenerate


class TestFixturesHealthyBaseline(unittest.TestCase):
    def test_health(self):
        snap = snapshot_from_summary(healthy_health_summary())
        self.assertEqual(gate_health_snapshot(snap).ok, 1)

    def test_doctor(self):
        self.assertEqual(run_doctor_gates(card=healthy_doctor_card())["ok"], 1)

    def test_cockpit(self):
        self.assertEqual(run_cockpit_gates(healthy_cockpit_knobs())["ok"], 1)

    def test_visualize(self):
        self.assertEqual(run_visualize_gates(topology=healthy_topology())["ok"], 1)

    def test_regen(self):
        self.assertEqual(run_weakest_regenerate(artefacts=artefact_set(), dry_run=True)["ok"], 1)


class TestFixturesHealthStatuses(unittest.TestCase):
    def test_all_healthy(self):
        statuses = ["healthy"] * len(REQUIRED_HEALTH_SURFACES)
        v = gate_health_snapshot(snapshot_from_summary(health_summary_with_statuses(statuses)))
        self.assertEqual(v.ok, 1)

    def test_each_one_failed(self):
        for i in range(len(REQUIRED_HEALTH_SURFACES)):
            statuses = ["healthy"] * len(REQUIRED_HEALTH_SURFACES)
            statuses[i] = "failed"
            v = gate_health_snapshot(snapshot_from_summary(health_summary_with_statuses(statuses)))
            self.assertEqual(v.ok, 0)


class TestFixturesDoctorCritical(unittest.TestCase):
    def test_all_domain_cards_red(self):
        for card in all_domain_critical_cards():
            self.assertEqual(run_doctor_gates(card=card)["ok"], 0)

    def test_warnings_under_ceiling(self):
        card = doctor_card_with_alerts(
            [warning_alert(REQUIRED_DOCTOR_DOMAINS[0], f"w{i}") for i in range(3)]
        )
        self.assertEqual(run_doctor_gates(card=card)["ok"], 1)


class TestFixturesCockpitOOR(unittest.TestCase):
    def test_all_oor_sets_red(self):
        for knobs in all_knob_oor_sets():
            self.assertEqual(run_cockpit_gates(knobs)["ok"], 0)

    def test_retune_recovers(self):
        for knobs in all_knob_oor_sets():
            r = run_cockpit_gates(knobs, auto_retune=True)
            self.assertEqual(r["ok"], 1)


class TestFixturesTopologySizes(unittest.TestCase):
    def test_chains(self):
        for n in range(2, 10):
            self.assertEqual(run_visualize_gates(topology=chain_topology(n))["ok"], 1)

    def test_grids(self):
        for w in range(2, 5):
            self.assertEqual(run_visualize_gates(topology=grid_topology(w))["ok"], 1)


class TestFixturesBridgeAndBundle(unittest.TestCase):
    def test_bridge_on_critical_cards(self):
        for card in all_domain_critical_cards():
            r = run_doctor_cockpit_bridge(doctor_card=card, apply=True)
            self.assertEqual(r["ok"], 1)
            self.assertTrue(r["plan"]["actions"])

    def test_ci_bundle(self):
        self.assertEqual(run_stu_tools_ci_bundle(doctor_card=healthy_doctor_card())["ok"], 1)

    def test_all_paths(self):
        self.assertEqual(run_all_paths(doctor_card=healthy_doctor_card())["ok"], 1)


if __name__ == "__main__":
    unittest.main()
