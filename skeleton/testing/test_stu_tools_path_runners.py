"""Path runner + catalog coverage regressions for STU-TOOLS deepen."""
from __future__ import annotations

import unittest
from typing import Any, Dict

from skeleton.developer.gate_catalog import CATALOG, gates_for_path
from skeleton.developer.path_runners import (
    run_all_paths,
    run_cockpit_path,
    run_doctor_path,
    run_health_path,
    run_regen_path,
    run_visualize_path,
)
from skeleton.developer.surface_inventory import REQUIRED_COCKPIT_KNOBS, REQUIRED_HEALTH_SURFACES


class TestPathRunnersGreen(unittest.TestCase):
    def test_health(self):
        r = run_health_path()
        self.assertEqual(r.ok, 1)
        self.assertEqual(r.stored_prose, 0)
        self.assertTrue(r.observed_gates)

    def test_visualize(self):
        r = run_visualize_path()
        self.assertEqual(r.ok, 1)

    def test_doctor(self):
        r = run_doctor_path()
        self.assertEqual(r.ok, 1)

    def test_cockpit(self):
        r = run_cockpit_path()
        self.assertEqual(r.ok, 1)

    def test_regen(self):
        r = run_regen_path()
        self.assertEqual(r.ok, 1)

    def test_all_paths(self):
        result = run_all_paths()
        self.assertEqual(result["ok"], 1)
        self.assertEqual(len(result["runs"]), 5)


class TestPathRunnersFailClosed(unittest.TestCase):
    def test_health_failed(self):
        class E:
            def summary(self):
                return {
                    "overall": "failed",
                    "total_subsystems": len(REQUIRED_HEALTH_SURFACES),
                    "phases_booted": len(REQUIRED_HEALTH_SURFACES),
                    "status_breakdown": {"failed": 1, "healthy": len(REQUIRED_HEALTH_SURFACES) - 1},
                    "cards": [
                        {
                            "name": n,
                            "status": "failed" if i == 0 else "healthy",
                            "phase": n,
                            "metrics": {},
                        }
                        for i, n in enumerate(REQUIRED_HEALTH_SURFACES)
                    ],
                }
        r = run_health_path(E())
        self.assertEqual(r.ok, 0)

    def test_visualize_empty(self):
        r = run_visualize_path({"name": "e", "components": {}, "wires": []})
        self.assertEqual(r.ok, 0)

    def test_cockpit_oor(self):
        knobs = {k: 1.0 for k in REQUIRED_COCKPIT_KNOBS}
        knobs["heat_mul"] = 9.0
        r = run_cockpit_path(knobs)
        self.assertEqual(r.ok, 0)

    def test_doctor_critical(self):
        card = {
            "alerts": [{"subsystem": "audit", "severity": "critical", "message": "x"}],
            "repair_effectiveness": {"ok": 1},
            "kv_cache": {"hit_rate": 0.9},
            "policy": {"enforced": 1},
            "circuit": {"open": 0},
            "health": {"overall": "healthy"},
            "audit_integrity": {"ok": 1},
            "dashboard": {"ready": 1},
            "cockpit": {k: 1.0 for k in REQUIRED_COCKPIT_KNOBS},
            "stored_prose": 0,
        }
        r = run_doctor_path(card)
        self.assertEqual(r.ok, 0)


class TestPathRunnerEnvelope(unittest.TestCase):
    def test_to_dict_keys(self):
        d = run_health_path().to_dict()
        for key in (
            "kind", "path", "ok", "banner", "duration_ms",
            "expected_gates", "observed_gates", "missing_gates", "payload", "stored_prose",
        ):
            self.assertIn(key, d)

    def test_expected_gates_match_catalog(self):
        for path, runner in (
            ("health", run_health_path),
            ("visualize", run_visualize_path),
            ("doctor", run_doctor_path),
            ("cockpit", run_cockpit_path),
            ("regen", run_regen_path),
        ):
            r = runner()
            expected = [g.name for g in gates_for_path(path)]
            self.assertEqual(r.expected_gates, expected)


class TestCatalogExhaustive(unittest.TestCase):
    def test_every_gate_has_description(self):
        for g in CATALOG:
            self.assertTrue(g.description)
            self.assertTrue(g.name)
            self.assertIn(g.severity, ("sev1", "sev2", "info"))

    def test_fail_closed_flags(self):
        for g in CATALOG:
            if g.severity in ("sev1", "sev2"):
                self.assertTrue(g.fail_closed)


if __name__ == "__main__":
    unittest.main()
