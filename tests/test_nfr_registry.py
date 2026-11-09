from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_nfr_registry",
    ROOT / "scripts" / "check_nfr_registry.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NFRRegistryTests(unittest.TestCase):
    def test_current_registry_is_valid(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["nfr_count"], 37)
        self.assertEqual(result["work_package_count"], 31)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="nfr-registry-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        for relative in (
            "machine/nfr_registry.json",
            "machine/ai_engineering_pass.json",
            "machine/ai_master_plan.json",
        ):
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, dst)
        return temp

    def test_rejects_fabricated_threshold(self) -> None:
        root = self._fixture()
        path = root / "machine/nfr_registry.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["nfrs"][0]["threshold_binding"]["values"] = {"threshold": 99}
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.NFRRegistryError, "may not fabricate"):
            MODULE.validate(root)

    def test_rejects_missing_budget_class(self) -> None:
        root = self._fixture()
        path = root / "machine/nfr_registry.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["nfrs"].pop()
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.NFRRegistryError, "coverage drift"):
            MODULE.validate(root)

    def test_measured_threshold_passes(self) -> None:
        root = self._fixture()
        registry = MODULE.validate(root)
        nfr_id = json.loads(
            (root / "machine/nfr_registry.json").read_text(encoding="utf-8")
        )["nfrs"][0]["nfr_id"]
        required = registry["required_measurement_fields"]
        binding = {field: "bound" for field in required}
        binding["threshold"] = 10
        measurements = {
            "measurements": [
                {
                    "nfr_id": nfr_id,
                    "binding": binding,
                    "measured_value": 9,
                    "comparator": "lte",
                    "result": "pass",
                }
            ]
        }
        path = root / "measurements.json"
        path.write_text(json.dumps(measurements), encoding="utf-8")
        result = MODULE.validate_measurements(root, Path("measurements.json"))
        self.assertEqual(result["measurement_status"], "valid")

    def test_measured_threshold_failure_is_non_compensable(self) -> None:
        root = self._fixture()
        registry = MODULE.validate(root)
        nfr_id = json.loads(
            (root / "machine/nfr_registry.json").read_text(encoding="utf-8")
        )["nfrs"][0]["nfr_id"]
        required = registry["required_measurement_fields"]
        binding = {field: "bound" for field in required}
        binding["threshold"] = 10
        measurements = {
            "measurements": [
                {
                    "nfr_id": nfr_id,
                    "binding": binding,
                    "measured_value": 11,
                    "comparator": "lte",
                    "result": "fail",
                }
            ]
        }
        path = root / "measurements.json"
        path.write_text(json.dumps(measurements), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.NFRRegistryError, "non-compensable"):
            MODULE.validate_measurements(root, Path("measurements.json"))


if __name__ == "__main__":
    unittest.main()
