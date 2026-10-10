from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_traceability_spine",
    ROOT / "scripts" / "check_traceability_spine.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TraceabilitySpineTests(unittest.TestCase):
    def test_current_spine_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["requirement_count"], 963)
        self.assertEqual(result["classified_volume_count"], 421)
        self.assertEqual(result["runtime_capability_count"], 9)
        self.assertEqual(result["nfr_count"], 37)
        self.assertEqual(result["behavior_count"], 32)
        self.assertEqual(result["state_machine_count"], 2)
        self.assertEqual(result["state_domain_count"], 21)
        self.assertEqual(result["interface_count"], 86)
        self.assertEqual(result["schema_count"], 40)
        self.assertEqual(result["compatibility_interface_count"], 86)
        self.assertEqual(result["protocol_count"], 4)
        self.assertEqual(result["maturity_entry_count"], 421)
        trace_index = json.loads(
            (ROOT / "machine/master_traceability.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            result["master_trace_node_count"],
            trace_index["summary"]["node_count"],
        )
        self.assertEqual(
            result["master_trace_edge_count"],
            trace_index["summary"]["edge_count"],
        )

    def test_impact_combines_trace_and_maturity_invalidation(self) -> None:
        result = MODULE.validate(
            ROOT,
            changed_files=["skeleton/api/server.py"],
        )
        impact = result["impact"]
        self.assertIn("VOL-004", impact["combined_impacted_volume_refs"])
        self.assertIn("VOL-004", impact["maturity_invalidated_volume_refs"])

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="trace-spine-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))

        files = (
            "machine/ai_master_plan.json",
            "machine/ai_build_accountability.json",
            "machine/ai_capabilities.json",
            "machine/ai_engineering_pass.json",
            "machine/state_topology.json",
            "machine/capability_interfaces.json",
            "machine/ai_runtime_schemas.json",
            "machine/contract_conformance.json",
            "machine/requirement_registry.json",
            "machine/capability_taxonomy.json",
            "machine/nfr_registry.json",
            "machine/behavior_specifications.json",
            "machine/state_machine_catalogue.json",
            "machine/interface_standard.json",
            "machine/schema_registry.json",
            "machine/compatibility_model.json",
            "machine/protocol_registry.json",
            "machine/maturity_registry.json",
            "machine/master_traceability.json",
            "scripts/check_nfr_registry.py",
            "scripts/check_master_traceability.py",
            "skeleton/contracts/operation.py",
            "skeleton/contracts/ai_execution.py",
            "skeleton/contracts/protocol.py",
            "skeleton/contracts/__init__.py",
            "skeleton/ai/runtime/contracts/protocol.py",
            "skeleton/ai/runtime/contracts/__init__.py",
            "skeleton/shells/worker_protocol.py",
            "skeleton/shells/ai/protocol.py",
            "skeleton/distributed/network/_replication_protocol.py",
        )
        for relative in files:
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        index = json.loads(
            (ROOT / "machine/master_traceability.json").read_text(encoding="utf-8")
        )
        for shard in index["shards"]:
            relative = shard["path"]
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    def test_rejects_requirement_text_drift(self) -> None:
        root = self._fixture()
        path = root / "machine/requirement_registry.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["requirements"][0]["text"] += " altered"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TraceSpineError, "requirement registry"):
            MODULE.validate(root)

    def test_rejects_capability_volume_coverage_loss(self) -> None:
        root = self._fixture()
        path = root / "machine/capability_taxonomy.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["volume_mappings"].pop()
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TraceSpineError, "volume coverage drift"):
            MODULE.validate(root)

    def test_rejects_protocol_mirror_drift(self) -> None:
        root = self._fixture()
        path = root / "skeleton/ai/runtime/contracts/protocol.py"
        path.write_text(
            path.read_text(encoding="utf-8") + "\n# drift\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MODULE.TraceSpineError, "protocol AI mirror drift"):
            MODULE.validate(root)

    def test_rejects_maturity_digest_drift(self) -> None:
        root = self._fixture()
        path = root / "machine/maturity_registry.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["entries"][0]["evidence_digest"] = "0" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TraceSpineError, "maturity evidence"):
            MODULE.validate(root)

    def test_rejects_schema_inventory_loss(self) -> None:
        root = self._fixture()
        path = root / "machine/schema_registry.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["schemas"].pop()
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TraceSpineError, "schema registry"):
            MODULE.validate(root)


if __name__ == "__main__":
    unittest.main()
