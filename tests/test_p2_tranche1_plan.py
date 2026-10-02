from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_p2_tranche1_plan",
    ROOT / "scripts" / "check_p2_tranche1_plan.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P2Tranche1PlanTests(unittest.TestCase):
    def test_current_prepared_plan_is_valid_and_fenced(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["selected_volume_count"], 15)
        self.assertEqual(result["workstream_count"], 5)
        self.assertEqual(result["tested_core_count"], 5)
        self.assertEqual(result["harness_gap_count"], 10)
        self.assertFalse(result["activation_ready"])
        self.assertIn("P2-NATIVE-01", result["activation_blockers"])
        self.assertEqual(result["remaining_queue_after_activation"], 257)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="p2-t1-plan-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        plan = json.loads(
            (ROOT / "machine/ai_p2_tranche1_plan.json").read_text(encoding="utf-8")
        )
        paths = {
            "machine/ai_p2_tranche1_plan.json",
            "machine/ai_master_plan.json",
            "machine/ai_p2_execution_map.json",
            "machine/ai_p2_task_backlog.json",
        }
        for item in plan["volume_selection_evidence"]:
            paths.update(item["existing_implementation_anchors"])
            paths.update(item["existing_test_anchors"])
        for relative in sorted(paths):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        return temp

    def test_rejects_premature_ownership(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["tasks"][0]["primary_volume_refs"].append("VOL-005")
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.P2Tranche1Error,
            "task ownership before activation",
        ):
            MODULE.validate(root)

    def test_rejects_selection_removed_from_queue(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_execution_map.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["first_tranche"]["queued_volume_refs"].remove("VOL-005")
        data["first_tranche"]["queued_volume_count"] -= 1
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.P2Tranche1Error,
            "source/first-tranche partition drift|not still queued",
        ):
            MODULE.validate(root)

    def test_rejects_narrowed_masterplan_obligation(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_tranche1_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        item = next(
            x for x in data["volume_selection_evidence"]
            if x["volume_ref"] == "VOL-026"
        )
        item["masterplan_obligation"]["risks"].pop()
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.P2Tranche1Error,
            "narrows/drifts masterplan field risks",
        ):
            MODULE.validate(root)

    def test_rejects_fake_existing_anchor(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_tranche1_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        item = next(
            x for x in data["volume_selection_evidence"]
            if x["volume_ref"] == "VOL-005"
        )
        item["existing_implementation_anchors"][0] = "planned:skeleton/not-real"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.P2Tranche1Error,
            "not canonical|does not exist",
        ):
            MODULE.validate(root)

    def test_rejects_workstream_cycle(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_tranche1_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["workstreams"][0]["depends_on"] = ["P2-T1-FUNCTIONAL"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.P2Tranche1Error,
            "dependency cycle",
        ):
            MODULE.validate(root)

    def test_status_only_native_landing_is_rejected_without_evidence(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        native = next(task for task in data["tasks"] if task["task_id"] == "P2-NATIVE-01")
        native["status"] = "landed_unpromoted"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.P2Tranche1Error,
            "full lowercase merge SHA|successful workflow evidence",
        ):
            MODULE.validate(root)

    def test_activation_becomes_ready_only_when_all_t0_landed_with_evidence(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for task in data["tasks"]:
            task["status"] = "landed_unpromoted"
        native = next(task for task in data["tasks"] if task["task_id"] == "P2-NATIVE-01")
        native["evidence_refs"] = [
            "dependency:P2-QUAL-01:landed_unpromoted",
            "github:pr#2332",
            "git:merge:" + ("a" * 40),
            "workflow:P2 Profile-Gated Acceleration@" + ("b" * 40) + ":success",
        ]
        path.write_text(json.dumps(data), encoding="utf-8")
        result = MODULE.validate(root)
        self.assertTrue(result["activation_ready"])
        self.assertEqual(result["activation_blockers"], [])


if __name__ == "__main__":
    unittest.main()
