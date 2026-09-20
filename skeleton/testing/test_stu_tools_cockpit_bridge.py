"""Tests for STU-TOOLS cockpit deepen, gates, bridge, catalog, CI bundle."""
from __future__ import annotations

import itertools
import json
import unittest
from typing import Any, Dict, List

from skeleton.developer.cockpit_deepen import (
    KNOB_RANGE,
    apply_retune,
    cockpit_diff,
    deepen_cockpit_report,
    render_cockpit_deep,
    retune_plan,
    snapshot_cockpit,
)
from skeleton.developer.cockpit_gates import (
    assert_cockpit_green,
    gate_cockpit_snapshot,
    run_cockpit_gates,
)
from skeleton.developer.doctor_cockpit_bridge import (
    DOMAIN_TO_KNOB,
    propose_bridge,
    run_doctor_cockpit_bridge,
)
from skeleton.developer.doctor_deepen import snapshot_from_doctor_card
from skeleton.developer.gate_catalog import (
    CATALOG,
    assert_catalog_covers,
    catalog_dict,
    catalog_fingerprint,
    gates_for_path,
    sev1_gates,
    sev2_gates,
)
from skeleton.developer.stu_tools_report import (
    build_coverage_card,
    build_merge_card,
    render_ci_bundle,
    run_stu_tools_ci_bundle,
)
from skeleton.developer.surface_inventory import REQUIRED_COCKPIT_KNOBS, REQUIRED_DOCTOR_DOMAINS
from skeleton.developer.stu_tools_pipeline import run_stu_tools_pipeline


def healthy_doctor() -> Dict[str, Any]:
    return {
        "alerts": [],
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


class TestCockpitDeepen(unittest.TestCase):
    def test_default_snapshot_green(self):
        snap = snapshot_cockpit()
        self.assertEqual(snap.stored_prose, 0)
        self.assertEqual(snap.out_of_range, [])
        self.assertGreaterEqual(snap.mean_score, 0.9)
        self.assertEqual(gate_cockpit_snapshot(snap).ok, 1)

    def test_out_of_range_detected(self):
        snap = snapshot_cockpit({"speed_mul": 9.0, "heat_mul": 1.0, "collapse_mul": 1.0})
        self.assertIn("speed_mul", snap.out_of_range)
        self.assertEqual(gate_cockpit_snapshot(snap).ok, 0)

    def test_non_numeric(self):
        snap = snapshot_cockpit({"speed_mul": "fast", "heat_mul": 1.0, "collapse_mul": 1.0})
        self.assertIn("speed_mul", snap.out_of_range)

    def test_stored_prose_law(self):
        snap = snapshot_cockpit({**{k: 1.0 for k in REQUIRED_COCKPIT_KNOBS}, "stored_prose": 4})
        self.assertEqual(snap.stored_prose, 4)
        self.assertEqual(gate_cockpit_snapshot(snap).ok, 0)

    def test_retune_clamps(self):
        snap = snapshot_cockpit({"speed_mul": 9.0, "heat_mul": 0.1, "collapse_mul": 1.0})
        plan = retune_plan(snap)
        self.assertIn("speed_mul", plan.clamps)
        self.assertIn("heat_mul", plan.clamps)
        after = apply_retune({"speed_mul": 9.0, "heat_mul": 0.1, "collapse_mul": 1.0}, plan)
        snap2 = snapshot_cockpit(after)
        self.assertEqual(snap2.out_of_range, [])

    def test_retune_zeros_prose(self):
        snap = snapshot_cockpit({**{k: 1.0 for k in REQUIRED_COCKPIT_KNOBS}, "stored_prose": 2})
        plan = retune_plan(snap)
        self.assertTrue(plan.zero_stored_prose)
        after = apply_retune({**{k: 1.0 for k in REQUIRED_COCKPIT_KNOBS}, "stored_prose": 2}, plan)
        self.assertEqual(after["stored_prose"], 0)

    def test_diff_regression(self):
        a = snapshot_cockpit()
        b = snapshot_cockpit({"speed_mul": 9.0, "heat_mul": 1.0, "collapse_mul": 1.0})
        d = cockpit_diff(a, b)
        self.assertTrue(d["regressed"])

    def test_deepen_and_render(self):
        report = deepen_cockpit_report()
        text = render_cockpit_deep(report)
        self.assertIn("Cockpit Deep", text)
        self.assertEqual(report["stored_prose"], 0)

    def test_run_gates_auto_retune(self):
        result = run_cockpit_gates(
            {"speed_mul": 9.0, "heat_mul": 1.0, "collapse_mul": 1.0},
            auto_retune=True,
        )
        assert_cockpit_green(result)
        self.assertIsNotNone(result["applied_knobs"])

    def test_knob_ranges_cover_required(self):
        for name in REQUIRED_COCKPIT_KNOBS:
            self.assertIn(name, KNOB_RANGE)


class TestDoctorCockpitBridge(unittest.TestCase):
    def test_healthy_bridge(self):
        doctor = snapshot_from_doctor_card(healthy_doctor())
        plan = propose_bridge(doctor)
        self.assertEqual(plan.stored_prose, 0)

    def test_critical_proposes_action(self):
        card = healthy_doctor()
        card["alerts"] = [{"subsystem": "repair", "severity": "critical", "message": "hot"}]
        doctor = snapshot_from_doctor_card(card)
        plan = propose_bridge(doctor)
        self.assertTrue(any(a.severity == "critical" for a in plan.actions))
        self.assertEqual(DOMAIN_TO_KNOB["repair"], "heat_mul")

    def test_run_bridge_gates(self):
        result = run_doctor_cockpit_bridge(doctor_card=healthy_doctor())
        self.assertEqual(result["ok"], 1)

    def test_run_bridge_apply(self):
        card = healthy_doctor()
        card["alerts"] = [{"subsystem": "policy", "severity": "critical", "message": "x"}]
        result = run_doctor_cockpit_bridge(doctor_card=card, apply=True)
        self.assertEqual(result["ok"], 1)
        self.assertIsNotNone(result["applied_knobs"])

    def test_domain_mapping_complete(self):
        for domain in REQUIRED_DOCTOR_DOMAINS:
            self.assertIn(domain, DOMAIN_TO_KNOB)


class TestGateCatalog(unittest.TestCase):
    def test_catalog_nonempty(self):
        self.assertGreaterEqual(len(CATALOG), 30)
        self.assertGreaterEqual(len(sev1_gates()), 10)
        self.assertGreaterEqual(len(sev2_gates()), 10)

    def test_paths_present(self):
        paths = {g.path for g in CATALOG}
        for required in ("health", "visualize", "doctor", "cockpit", "regen"):
            self.assertIn(required, paths)

    def test_catalog_dict_shape(self):
        d = catalog_dict()
        self.assertEqual(d["kind"], "stu-tools-gate-catalog")
        self.assertEqual(d["stored_prose"], 0)
        self.assertEqual(d["count"], len(CATALOG))

    def test_fingerprint_stable(self):
        self.assertEqual(catalog_fingerprint(), catalog_fingerprint())

    def test_assert_covers(self):
        names = [g.name for g in gates_for_path("doctor")]
        assert_catalog_covers(names, path="doctor")

    def test_assert_covers_missing_raises(self):
        with self.assertRaises(AssertionError):
            assert_catalog_covers(["not.a.real.gate"])


class TestCiBundle(unittest.TestCase):
    def test_bundle_green(self):
        bundle = run_stu_tools_ci_bundle()
        self.assertEqual(bundle["ok"], 1, msg=bundle.get("banner"))
        self.assertEqual(bundle["stored_prose"], 0)
        self.assertIn("merge_card", bundle)
        self.assertIn("coverage", bundle)

    def test_merge_card_from_pipeline(self):
        pipe = run_stu_tools_pipeline()
        card = build_merge_card(pipe)
        self.assertEqual(card["ok"], 1)
        self.assertEqual(card["stored_prose"], 0)

    def test_coverage_card(self):
        card = build_coverage_card()
        self.assertGreaterEqual(card["gate_count"], 30)

    def test_render_bundle(self):
        text = render_ci_bundle(run_stu_tools_ci_bundle())
        self.assertIn("CI Bundle", text)

    def test_json_serializable(self):
        raw = json.dumps(run_stu_tools_ci_bundle(), default=str)
        self.assertIn("stu-tools-ci-bundle", raw)


class TestCockpitCombinatorics(unittest.TestCase):
    def test_each_knob_high_low(self):
        for knob, (lo, hi) in KNOB_RANGE.items():
            for value in (lo - 0.1, lo, 1.0, hi, hi + 0.1):
                knobs = {k: 1.0 for k in REQUIRED_COCKPIT_KNOBS}
                knobs[knob] = value
                snap = snapshot_cockpit(knobs)
                v = gate_cockpit_snapshot(snap)
                expect_fail = value < lo or value > hi
                if expect_fail:
                    self.assertEqual(v.ok, 0, msg=f"{knob}={value}")
                else:
                    self.assertEqual(v.ok, 1, msg=f"{knob}={value}")

    def test_bridge_each_domain_critical(self):
        for domain in REQUIRED_DOCTOR_DOMAINS:
            card = healthy_doctor()
            card["alerts"] = [{"subsystem": domain, "severity": "critical", "message": "x"}]
            result = run_doctor_cockpit_bridge(doctor_card=card, apply=True)
            self.assertEqual(result["ok"], 1, msg=domain)
            self.assertTrue(result["plan"]["actions"])


class TestCommandsCockpitBridge(unittest.TestCase):
    def test_registry(self):
        from skeleton.developer.commands import _dev_registry
        for name in ("cockpit", "bridge", "doctor", "stu-tools"):
            self.assertIn(name, _dev_registry.commands)

    def test_cockpit_command(self):
        from skeleton.developer.commands import CockpitCommand
        result = CockpitCommand()(["--gates", "--json"])
        self.assertEqual(result["ok"], 1)

    def test_bridge_command(self):
        from skeleton.developer.commands import BridgeCommand
        result = BridgeCommand()(["--json"])
        self.assertEqual(result["ok"], 1)

    def test_stu_tools_ci_bundle_flag(self):
        from skeleton.developer.commands import StuToolsCommand
        result = StuToolsCommand()(["--json", "--ci-bundle"])
        self.assertEqual(result["kind"], "stu-tools-ci-bundle")
        self.assertEqual(result["ok"], 1)


if __name__ == "__main__":
    unittest.main()
