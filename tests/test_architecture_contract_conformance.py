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
        self.assertEqual(result["contract_count"], 36)
        self.assertEqual(result["override_count"], 3)
        self.assertEqual(result["executed_vector_count"], result["vector_count"])

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


if __name__ == "__main__":
    unittest.main()
