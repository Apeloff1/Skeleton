from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_p2_acceleration",
    ROOT / "scripts" / "check_p2_acceleration.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P2AccelerationControlTests(unittest.TestCase):
    def test_current_policy_is_valid_and_unpromoted(self) -> None:
        result = MODULE.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["masterplan_binding_count"], 2)
        self.assertEqual(result["promoted_candidate_count"], 0)
        self.assertEqual(result["activated_candidate_count"], 0)
        self.assertGreaterEqual(result["jvm_candidate_count"], 1)

    def _fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="p2-acceleration-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        policy = json.loads((ROOT / "machine/acceleration_policy.json").read_text(encoding="utf-8"))
        paths = {
            "machine/acceleration_policy.json",
            "machine/ai_master_plan.json",
            "skeleton/native/selection.py",
            "skeleton/native/isolation.py",
            "skeleton/native/protocol.py",
            "skeleton/native/profiling.py",
            "skeleton/ai/runtime/native/selection.py",
            "skeleton/ai/runtime/native/isolation.py",
            "skeleton/ai/runtime/native/protocol.py",
            "skeleton/ai/runtime/native/profiling.py",
            "scripts/profile_p2_acceleration.py",
        }
        paths.update(policy["runtime_authority"].values())
        for candidate in policy["candidates"]:
            paths.add(candidate["implementation"])
            paths.add(candidate["registry"])
            paths.update(candidate["reference_paths"])
            paths.update(candidate["source_identity_paths"])
        for relative in sorted(paths):
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        return temp

    def test_rejects_compensable_error_tolerance(self) -> None:
        root = self._fixture()
        path = root / "machine/acceleration_policy.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["selection_policy"]["non_compensable"].remove("error tolerance")
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.AccelerationControlError,
            "non-compensable selection gates drift",
        ):
            MODULE.validate(root)

    def test_rejects_boolean_or_negative_numeric_qualification_bounds(self) -> None:
        root = self._fixture()
        path = root / "machine/acceleration_policy.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["selection_policy"]["maximum_abs_error"] = -1
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.AccelerationControlError,
            "maximum_abs_error",
        ):
            MODULE.validate(root)

    def test_rejects_evidence_free_auto_selection(self) -> None:
        root = self._fixture()
        path = root / "machine/acceleration_policy.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["candidates"][0]["automatic_selection"] = True
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.AccelerationControlError,
            "cannot auto-select without evidence",
        ):
            MODULE.validate(root)

    def test_rejects_inprocess_medium_risk_candidate(self) -> None:
        root = self._fixture()
        path = root / "machine/acceleration_policy.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["candidates"][0]["isolation"] = "in_process"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.AccelerationControlError,
            "must use subprocess isolation",
        ):
            MODULE.validate(root)

    def test_rejects_jvm_protocol_drift(self) -> None:
        root = self._fixture()
        path = root / "machine/acceleration_policy.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidate = next(x for x in payload["candidates"] if x["plane"] == "jvm")
        candidate["protocol"] = "unversioned"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.AccelerationControlError,
            "JVM protocol negotiation drift",
        ):
            MODULE.validate(root)


if __name__ == "__main__":
    unittest.main()
