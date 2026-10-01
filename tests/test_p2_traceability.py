from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_p2_traceability",
    ROOT / "scripts" / "check_p2_traceability.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P2TraceabilityTests(unittest.TestCase):
    def test_current_traceability_spine_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["trace_volume_count"], 12)
        self.assertEqual(result["requirement_count"], 50)
        self.assertEqual(result["schema_count"], 36)
        self.assertEqual(result["behavior_count"], 12)
        self.assertEqual(result["protocol_count"], 4)
        self.assertEqual(result["nfr_metrics"]["dangling_trace_edges"], 0.0)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="p2-trace-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        files = (
            "machine/ai_master_plan.json",
            "machine/ai_build_accountability.json",
            "machine/capability_interfaces.json",
            "machine/ai_runtime_schemas.json",
            "machine/master_traceability.json",
            "machine/requirement_registry.json",
            "machine/capability_taxonomy.json",
            "machine/capability_registry.json",
            "machine/capability_maturity.json",
            "machine/behavior_specifications.json",
            "machine/state_machine_catalogue.json",
            "machine/interface_standard.json",
            "machine/schema_registry.json",
            "machine/compatibility_model.json",
            "machine/internal_protocols.json",
            "machine/nfr_registry.json",
            "scripts/check_p2_traceability.py",
            "tests/test_p2_traceability.py",
            "skeleton/contracts/operation.py",
            "skeleton/contracts/ai_execution.py",
            "skeleton/testing/test_operation_runtime.py",
        )
        for relative in files:
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    def test_rejects_masterplan_requirement_drift(self) -> None:
        root = self._fixture()
        path = root / "machine/requirement_registry.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["requirements"][0]["text"] = "narrowed text"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TraceabilityError, "text drift"):
            MODULE.validate(root)

    def test_rejects_unmapped_masterplan_volume(self) -> None:
        root = self._fixture()
        path = root / "machine/capability_taxonomy.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["volume_map"].pop()
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.TraceabilityError,
            "must map every masterplan volume",
        ):
            MODULE.validate(root)

    def test_rejects_stale_maturity_digest(self) -> None:
        root = self._fixture()
        path = root / "machine/capability_maturity.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["sources"]["accountability"]["git_blob_sha"] = "0" * 40
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.TraceabilityError,
            "accountability digest is stale",
        ):
            MODULE.validate(root)

    def test_rejects_dangling_trace_edge(self) -> None:
        root = self._fixture()
        path = root / "machine/master_traceability.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["edges"][0]["to"] = "REQ-DOES-NOT-EXIST"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TraceabilityError, "dangling edges"):
            MODULE.validate(root)

    def test_rejects_missing_interface_failure_contract(self) -> None:
        root = self._fixture()
        path = root / "machine/capability_interfaces.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["entries"][0]["target_failure_contract"] = ""
        path.write_text(json.dumps(data), encoding="utf-8")

        # This test targets interface semantics, not the earlier source-digest
        # invalidation gates. Refresh the dependent snapshot digests so
        # validation reaches the interface rule itself.
        digest = MODULE._git_blob_sha(path)
        for relative in (
            "machine/capability_registry.json",
            "machine/interface_standard.json",
        ):
            dependent = root / relative
            payload = json.loads(dependent.read_text(encoding="utf-8"))
            payload["source_git_blob_sha"] = digest
            dependent.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(MODULE.TraceabilityError, "missing interface field"):
            MODULE.validate(root)

    def test_rejects_schema_inventory_loss(self) -> None:
        root = self._fixture()
        path = root / "machine/schema_registry.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["schemas"].pop()
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TraceabilityError, "coverage drift"):
            MODULE.validate(root)

    def test_rejects_protocol_schema_drift(self) -> None:
        root = self._fixture()
        path = root / "machine/internal_protocols.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["protocols"][0]["envelope_schemas"].append("NotARealSchema")
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.TraceabilityError,
            "unregistered schemas",
        ):
            MODULE.validate(root)

    def test_change_impact_maps_authority_to_volume(self) -> None:
        graph = json.loads(
            (ROOT / "machine/master_traceability.json").read_text(encoding="utf-8")
        )
        impact = MODULE._impact(
            graph,
            ["machine/schema_registry.json", "README.md"],
        )
        self.assertIn("VOL-129", impact["impacted_volumes"])
        self.assertEqual(
            impact["matched_authorities"]["machine/schema_registry.json"],
            "AUTH-SCHEMA",
        )


if __name__ == "__main__":
    unittest.main()
