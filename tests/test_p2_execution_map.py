from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_p2_execution_map", ROOT / "scripts" / "check_p2_execution_map.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P2ExecutionMapTests(unittest.TestCase):
    def test_current_repository_map_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["source_volume_count"], 314)
        self.assertEqual(result["scheduled_volume_count"], 57)
        self.assertEqual(result["queued_volume_count"], 257)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="p2-map-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        for relative in (
            "machine/ai_master_plan.json",
            "machine/ai_master_build_sequence.json",
            "machine/ai_p1_execution_map.json",
            "machine/ai_p2_execution_map.json",
            "machine/ai_p2_task_backlog.json",
        ):
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, dst)
        return temp

    def test_rejects_silent_scope_loss(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_execution_map.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["source_scope"]["volume_refs"].pop()
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, "must equal P1 deferred scope"):
            MODULE.validate(root)

    def test_rejects_double_owned_scheduled_volume(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        first = data["tasks"][1]["primary_volume_refs"][0]
        data["tasks"][2]["primary_volume_refs"].append(first)
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, "multiple owners"):
            MODULE.validate(root)

    def test_rejects_task_dependency_cycle(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["tasks"][0]["depends_on"] = ["P2-NATIVE-01"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, "dependency cycle"):
            MODULE.validate(root)

    def test_rejects_fabricated_completion(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["tasks"][0]["completion_checkbox"] = True
        data["tasks"][0]["completion_checkbox_mark"] = "[x]"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, "may not assert completion"):
            MODULE.validate(root)

    def test_rejects_narrowed_masterplan_risk(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        obligation = data["tasks"][1]["masterplan_obligations"][0]
        obligation["risks"] = obligation["risks"][:-1]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, "narrows/drifts masterplan"):
            MODULE.validate(root)

    def test_rejects_breadth_freeze_override(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_execution_map.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["masterplan_alignment"]["breadth_freeze"]["required_enabled"] = False
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, "must require the masterplan breadth freeze"):
            MODULE.validate(root)

    def test_rejects_master_build_sequence_drift(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_execution_map.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["masterplan_alignment"]["master_build_sequence"]["required_wave_count"] = 7
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, "wave count drift"):
            MODULE.validate(root)

    def test_rejects_ready_task_with_unlanded_dependency(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        by_id = {task["task_id"]: task for task in data["tasks"]}
        by_id["P2-TRACE-01"]["status"] = "in_progress"
        by_id["P2-REPO-01"]["status"] = "ready"
        data["summary"]["in_progress_count"] = 1
        data["summary"]["ready_count"] = 3
        data["summary"]["landed_unpromoted_count"] = 2
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, "unresolved dependencies"):
            MODULE.validate(root)

    def test_rejects_blocked_task_when_dependencies_are_landed(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        by_id = {task["task_id"]: task for task in data["tasks"]}
        by_id["P2-REPO-01"]["status"] = "blocked"
        data["summary"]["ready_count"] = 2
        data["summary"]["blocked_count"] = 2
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, "all dependencies are landed"):
            MODULE.validate(root)

    def test_rejects_stale_progress_projection(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_execution_map.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["progress"]["landed_unpromoted_tasks"] = data["progress"][
            "landed_unpromoted_tasks"
        ][:-1]
        data["progress"]["active_tasks"] = ["P2-T1-FUNCTIONAL-01"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.P2ValidationError,
            "progress .* drift",
        ):
            MODULE.validate(root)

    def test_rejects_progress_task_double_count(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_execution_map.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["progress"]["active_tasks"] = [
            data["progress"]["landed_unpromoted_tasks"][0]
        ]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.P2ValidationError,
            "progress active_tasks drift|cover each task exactly once",
        ):
            MODULE.validate(root)

    def test_rejects_landed_task_without_evidence(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        by_id = {task["task_id"]: task for task in data["tasks"]}
        by_id["P2-TRACE-01"]["evidence_refs"] = []
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, "requires at least three evidence refs"):
            MODULE.validate(root)


    def test_security_tranche_owns_every_scheduled_security_volume(self) -> None:
        master = json.loads((ROOT / "machine/ai_master_plan.json").read_text(encoding="utf-8"))
        backlog = json.loads((ROOT / "machine/ai_p2_task_backlog.json").read_text(encoding="utf-8"))
        task = next(t for t in backlog["tasks"] if t["task_id"] == "P2-T1-SEC-01")
        refs = ["VOL-026", "VOL-027", "VOL-167", "VOL-169", "VOL-172", "VOL-175"]
        self.assertEqual(task["primary_volume_refs"], refs)
        self.assertEqual([o["volume_ref"] for o in task["masterplan_obligations"]], refs)
        canonical = {v["key"]: v for v in master["volumes"]}
        for obligation in task["masterplan_obligations"]:
            with self.subTest(volume=obligation["volume_ref"]):
                source = canonical[obligation["volume_ref"]]
                for field in (
                    "gaps", "risks", "contracts", "implementation_status",
                    "completion_checkbox", "implementation_paths", "tests", "evaluations",
                ):
                    self.assertEqual(obligation[field], source[field])
        for ref in refs[-4:]:
            self.assertEqual(canonical[ref]["implementation_status"], "unverified")
            self.assertFalse(canonical[ref]["completion_checkbox"])
            self.assertTrue(canonical[ref]["gaps"])
        self.assertFalse(task["completion_checkbox"])
        self.assertFalse(task["implementation_signed"])
        self.assertFalse(task["verification_signed"])

    def test_rejects_unowned_security_volume(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        security = next(t for t in data["tasks"] if t["task_id"] == "P2-T1-SEC-01")
        security["primary_volume_refs"].remove("VOL-172")
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, "task ownership must equal scheduled set"):
            MODULE.validate(root)

    def test_rejects_narrowed_security_egress_tests(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_p2_task_backlog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        security = next(t for t in data["tasks"] if t["task_id"] == "P2-T1-SEC-01")
        obligation = next(o for o in security["masterplan_obligations"] if o["volume_ref"] == "VOL-172")
        obligation["tests"] = []
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, r"narrows/drifts masterplan VOL-172.tests"):
            MODULE.validate(root)

    def test_verified_volume_does_not_promote_unsigned_task(self) -> None:
        master = json.loads((ROOT / "machine/ai_master_plan.json").read_text(encoding="utf-8"))
        backlog = json.loads((ROOT / "machine/ai_p2_task_backlog.json").read_text(encoding="utf-8"))
        architecture = next(v for v in master["volumes"] if v["key"] == "VOL-002")
        self.assertTrue(architecture["completion_checkbox"])
        self.assertEqual(architecture["implementation_status"], "verified")
        self.assertTrue(architecture["evidence"])
        task = next(t for t in backlog["tasks"] if t["task_id"] == "P2-ARCH-01")
        obligation = next(o for o in task["masterplan_obligations"] if o["volume_ref"] == "VOL-002")
        self.assertTrue(obligation["completion_checkbox"])
        self.assertFalse(task["completion_checkbox"])
        self.assertFalse(task["verification_signed"])

    def test_rejects_verified_volume_without_canonical_evidence(self) -> None:
        root = self._fixture()
        plan_path = root / "machine/ai_master_plan.json"
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        architecture = next(v for v in data["volumes"] if v["key"] == "VOL-002")
        architecture["evidence"] = []
        plan_path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.P2ValidationError, "claims completion without verified implementation and evidence"):
            MODULE.validate(root)


if __name__ == "__main__":
    unittest.main()
