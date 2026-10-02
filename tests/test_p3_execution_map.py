from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.check_p3_execution_map import P3ValidationError, validate


ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "machine/ai_master_plan.json",
    "machine/ai_p2_execution_map.json",
    "machine/ai_p2_functional_ai_closure.json",
    "machine/ai_p3_tranche0_plan.json",
    "machine/ai_p3_execution_map.json",
    "machine/ai_p3_task_backlog.json",
)


class P3ExecutionMapTests(unittest.TestCase):
    def test_current_repository_map_is_valid(self) -> None:
        result = validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["source_volume_count"], 257)
        self.assertEqual(result["scheduled_volume_count"], 23)
        self.assertEqual(result["queued_volume_count"], 234)
        self.assertEqual(result["task_count"], 6)
        self.assertEqual(result["ready_count"], 0)
        self.assertEqual(result["blocked_count"], 3)
        self.assertEqual(result["parent_functional_frontier"], "closed")

    def _fixture(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="p3-map-"))
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        for rel in FILES:
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dst)
        return root

    def _load(self, root: Path, rel: str) -> tuple[Path, dict]:
        path = root / rel
        return path, json.loads(path.read_text(encoding="utf-8"))

    def test_rejects_p2_source_scope_drift(self) -> None:
        root = self._fixture()
        path, payload = self._load(root, "machine/ai_p3_execution_map.json")
        payload["source_scope"]["volume_refs"].pop()
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(P3ValidationError, "exactly equal P2 queued scope"):
            validate(root)

    def test_rejects_silent_queue_loss(self) -> None:
        root = self._fixture()
        path, payload = self._load(root, "machine/ai_p3_execution_map.json")
        payload["first_tranche"]["queued_volume_refs"].pop()
        payload["first_tranche"]["queued_volume_count"] -= 1
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(P3ValidationError, "cover source exactly"):
            validate(root)

    def test_rejects_double_owned_volume(self) -> None:
        root = self._fixture()
        path, payload = self._load(root, "machine/ai_p3_task_backlog.json")
        payload["tasks"][1]["primary_volume_refs"].append(
            payload["tasks"][0]["primary_volume_refs"][0]
        )
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(P3ValidationError):
            validate(root)

    def test_rejects_narrowed_masterplan_obligation(self) -> None:
        root = self._fixture()
        path, payload = self._load(root, "machine/ai_p3_task_backlog.json")
        payload["tasks"][0]["masterplan_obligations"][0]["risks"].pop()
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(P3ValidationError, "narrows/drifts"):
            validate(root)

    def test_rejects_self_signoff(self) -> None:
        root = self._fixture()
        path, payload = self._load(root, "machine/ai_p3_task_backlog.json")
        payload["tasks"][0]["verification_signed"] = True
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(P3ValidationError, "self-complete or self-sign"):
            validate(root)

    def test_rejects_ready_task_with_unlanded_dependencies(self) -> None:
        root = self._fixture()
        path, payload = self._load(root, "machine/ai_p3_task_backlog.json")
        task = next(
            item
            for item in payload["tasks"]
            if item["task_id"] == "P3-VERTICAL-SUITE-01"
        )
        task["status"] = "ready"
        payload["summary"]["ready_count"] = 1
        payload["summary"]["blocked_count"] = 2
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(P3ValidationError, "unresolved dependencies"):
            validate(root)

    def test_rejects_parent_functional_frontier_reopen(self) -> None:
        root = self._fixture()
        path, payload = self._load(root, "machine/ai_p2_functional_ai_closure.json")
        payload["status"] = "active"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(P3ValidationError, "requires closed P2"):
            validate(root)


if __name__ == "__main__":
    unittest.main()
