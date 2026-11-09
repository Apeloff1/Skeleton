from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_master_traceability",
    ROOT / "scripts" / "check_master_traceability.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MasterTraceabilityTests(unittest.TestCase):
    def test_current_graph_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["volume_count"], 421)
        self.assertEqual(result["node_count"], 9115)
        self.assertEqual(result["edge_count"], 25119)
        self.assertEqual(result["requirement_count"], 963)
        self.assertEqual(result["requirements_without_tests"], [])
        self.assertEqual(result["requirements_without_evidence_count"], 688)

    def test_change_impact_resolves_runtime_path(self) -> None:
        result = MODULE.impact(ROOT, ["skeleton/api/server.py"])
        self.assertIn("VOL-004", result["impacted_volume_refs"])
        self.assertEqual(result["unmapped_changed_files"], [])

    def test_unknown_path_is_reported_unmapped(self) -> None:
        result = MODULE.impact(ROOT, ["mystery/unowned.txt"])
        self.assertEqual(result["impacted_volume_refs"], [])
        self.assertEqual(result["unmapped_changed_files"], ["mystery/unowned.txt"])

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="master-trace-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        for relative in ("machine/master_traceability.json", "machine/ai_master_plan.json"):
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, dst)
        index = json.loads((temp / "machine/master_traceability.json").read_text(encoding="utf-8"))
        for shard in index["shards"]:
            src = ROOT / shard["path"]
            dst = temp / shard["path"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    def test_rejects_missing_shard(self) -> None:
        root = self._fixture()
        path = root / "machine/master_traceability.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["shards"].pop()
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TraceabilityError, "depth coverage drift"):
            MODULE.validate(root)

    def test_rejects_stale_node(self) -> None:
        root = self._fixture()
        index = json.loads((root / "machine/master_traceability.json").read_text(encoding="utf-8"))
        shard_path = root / index["shards"][0]["path"]
        shard = json.loads(shard_path.read_text(encoding="utf-8"))
        target = next(node for node in shard["nodes"] if node["type"] == "requirement")
        target["value"] = target["value"] + " drift"
        shard_path.write_text(json.dumps(shard), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TraceabilityError, "node content is stale"):
            MODULE.validate(root)

    def test_rejects_dangling_edge(self) -> None:
        root = self._fixture()
        index = json.loads((root / "machine/master_traceability.json").read_text(encoding="utf-8"))
        shard_path = root / index["shards"][0]["path"]
        shard = json.loads(shard_path.read_text(encoding="utf-8"))
        shard["edges"][0]["to"] = "MISSING:NODE"
        shard_path.write_text(json.dumps(shard), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TraceabilityError, "edge content is stale"):
            MODULE.validate(root)


if __name__ == "__main__":
    unittest.main()
