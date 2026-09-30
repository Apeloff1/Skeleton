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
        self.assertEqual(result["scheduled_volume_count"], 42)
        self.assertEqual(result["queued_volume_count"], 272)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="p2-map-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        for relative in (
            "machine/ai_master_plan.json",
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


if __name__ == "__main__":
    unittest.main()
