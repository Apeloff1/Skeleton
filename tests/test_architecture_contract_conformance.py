from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_architecture_contract_conformance",
    ROOT / "scripts" / "check_architecture_contract_conformance.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ContractConformanceTests(unittest.TestCase):
    def test_current_catalog_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["contract_count"], 40)
        self.assertEqual(result["override_count"], 3)
        self.assertEqual(result["executed_vector_count"], result["vector_count"])
        self.assertEqual(result["authority_scope"], "contract-conformance-only")
        self.assertEqual(len(result["qualification_digest"]), 64)
        self.assertEqual(set(result["source_digests"]), {"catalog", "schema_catalog", "interface_registry"})

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="contract-conformance-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        for relative in (
            "machine/contract_conformance.json",
            "machine/ai_runtime_schemas.json",
            "machine/capability_interfaces.json",
            "machine/ai_master_plan.json",
        ):
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, dst)
        return temp

    def test_rejects_missing_contract_inventory(self) -> None:
        root = self._fixture()
        path = root / "machine/contract_conformance.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["entries"].pop()
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractConformanceError, "cover schema records exactly"):
            MODULE.validate(root)

    def test_rejects_unjustified_override(self) -> None:
        root = self._fixture()
        path = root / "machine/contract_conformance.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        entry = next(e for e in data["entries"] if e["contract"] == "ResourceBudget")
        entry["override_rationale"] = ""
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractConformanceError, "override requires rationale"):
            MODULE.validate(root)

    def test_rejects_vector_expectation_drift(self) -> None:
        root = self._fixture()
        path = root / "machine/contract_conformance.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        vector = next(v for v in data["vectors"] if v["id"] == "JSON-DUPLICATE-KEY")
        vector["expected"] = "accept"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractConformanceError, "expected accept"):
            MODULE.validate(root)

    def test_qualification_digest_changes_with_schema_source_identity(self) -> None:
        root = self._fixture()
        before = MODULE.validate(root)
        path = root / "machine/ai_runtime_schemas.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["qualification_probe"] = "identity-only"
        path.write_text(json.dumps(data), encoding="utf-8")
        after = MODULE.validate(root)
        self.assertNotEqual(before["source_digests"]["schema_catalog"], after["source_digests"]["schema_catalog"])
        self.assertNotEqual(before["qualification_digest"], after["qualification_digest"])

    def test_qualification_digest_changes_with_interface_source_identity(self) -> None:
        root = self._fixture()
        before = MODULE.validate(root)
        path = root / "machine/capability_interfaces.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["qualification_probe"] = "identity-only"
        path.write_text(json.dumps(data), encoding="utf-8")
        after = MODULE.validate(root)
        self.assertNotEqual(before["source_digests"]["interface_registry"], after["source_digests"]["interface_registry"])
        self.assertNotEqual(before["qualification_digest"], after["qualification_digest"])


    def test_pending_exact_head_qualification_state_is_valid(self) -> None:
        root = self._fixture()
        result = MODULE.validate(root)
        self.assertEqual(result["masterplan_binding"], "VOL-003")

    def test_rejects_retired_implementation_gap_reappearance(self) -> None:
        root = self._fixture()
        catalog_path = root / "machine/contract_conformance.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        retired = catalog["masterplan_binding"]["retired_implementation_gaps"][0]
        path = root / "machine/ai_master_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        volume = next(row for row in data["volumes"] if row["key"] == "VOL-003")
        volume["gaps"] = [retired]
        volume["completion_checkbox"] = False
        volume["completion_checkbox_mark"] = "[ ]"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.ContractConformanceError,
            "gap state must be pending exact-head qualification or signed",
        ):
            MODULE.validate(root)

    def test_rejects_cleared_qualification_without_signoff(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_master_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        volume = next(row for row in data["volumes"] if row["key"] == "VOL-003")
        volume["gaps"] = []
        volume["completion_checkbox"] = False
        volume["completion_checkbox_mark"] = "[ ]"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.ContractConformanceError,
            "cannot clear qualification gap before completion signoff",
        ):
            MODULE.validate(root)

    def test_signed_exact_head_closure_state_is_valid(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_master_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        volume = next(row for row in data["volumes"] if row["key"] == "VOL-003")
        volume["gaps"] = []
        volume["completion_checkbox"] = True
        volume["completion_checkbox_mark"] = "[x]"
        volume["implementation_status"] = "verified"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = MODULE.validate(root)
        self.assertEqual(result["masterplan_binding"], "VOL-003")

    def test_rejects_signed_state_with_pending_qualification_gap(self) -> None:
        root = self._fixture()
        path = root / "machine/ai_master_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        volume = next(row for row in data["volumes"] if row["key"] == "VOL-003")
        volume["completion_checkbox"] = True
        volume["completion_checkbox_mark"] = "[x]"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.ContractConformanceError,
            "cannot remain signed with a pending qualification gap",
        ):
            MODULE.validate(root)

if __name__ == "__main__":
    unittest.main()
