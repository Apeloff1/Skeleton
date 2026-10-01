from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_architecture_runtime_supervision",
    ROOT / "scripts" / "check_architecture_runtime_supervision.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RuntimeSupervisionTests(unittest.TestCase):
    def test_current_supervision_contract_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["service_count"], 2)
        self.assertGreater(result["required_symbol_count"], 10)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="runtime-supervision-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        contract = json.loads((ROOT / "machine/runtime_supervision.json").read_text(encoding="utf-8"))
        paths = {
            "machine/runtime_supervision.json",
            "machine/ai_master_plan.json",
            contract["sources"]["runtime_manifest"],
        }
        for service in contract["services"]:
            for group in ("lifecycle_bindings", "connector_bindings", "cancellation_bindings"):
                for item in service.get(group, []):
                    paths.add(item["path"])
        for relative in sorted(paths):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return temp

    def test_rejects_manifest_dependency_drift(self) -> None:
        root = self._fixture()
        path = root / "skeleton/app/manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        backend = next(s for s in data["services"] if s["name"] == "backend")
        backend["depends_on"] = ["mongo"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.RuntimeSupervisionError, "dependency drift"):
            MODULE.validate(root)

    def test_rejects_missing_cancel_binding(self) -> None:
        root = self._fixture()
        path = root / "backend/core/engine_client.py"
        text = path.read_text(encoding="utf-8").replace(
            'f"/executions/{execution}/cancel"',
            'f"/executions/{execution}/removed"',
        )
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(MODULE.RuntimeSupervisionError, "required runtime symbol missing"):
            MODULE.validate(root)

    def test_rejects_stale_masterplan_gap(self) -> None:
        root = self._fixture()
        path = root / "machine/runtime_supervision.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["masterplan_binding"]["required_gap_texts"][0] = "not a real gap"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.RuntimeSupervisionError, "masterplan gap drift"):
            MODULE.validate(root)


if __name__ == "__main__":
    unittest.main()
