"""Regression tests for the Expo SDK/React/React Native pairing gate."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_expo_runtime_pairing import ROOT, main, validate


def manifest() -> dict:
    return {
        "dependencies": {
            "expo": "~54.0.35",
            "react-native": "0.81.5",
            "react": "19.1.0",
            "react-dom": "19.1.0",
            "react-native-web": "~0.21.0",
            "@types/react": "~19.1.0",
        }
    }


class ExpoPairingContract(unittest.TestCase):
    def test_current_repository_manifest_is_supported(self) -> None:
        current = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(validate(current), [])

    def test_documented_sdk54_pairing_passes(self) -> None:
        self.assertEqual(validate(manifest()), [])

    def test_rejects_cross_sdk_react_native_jump(self) -> None:
        data = manifest()
        data["dependencies"]["react-native"] = "0.88.0"
        self.assertIn("react-native: Expo SDK 54 requires 0.81.x", " ".join(validate(data)))

    def test_rejects_cross_sdk_react_jump(self) -> None:
        data = manifest()
        data["dependencies"]["react"] = "19.3.1"
        self.assertIn("react: Expo SDK 54 requires 19.1.x", " ".join(validate(data)))

    def test_rejects_mismatched_react_dom(self) -> None:
        data = manifest()
        data["dependencies"]["react-dom"] = "19.1.1"
        self.assertTrue(any("must exactly equal react" in error for error in validate(data)))

    def test_rejects_ranged_native_runtime(self) -> None:
        data = manifest()
        data["dependencies"]["react-native"] = "^0.81.5"
        self.assertTrue(any("exact pin required" in error for error in validate(data)))

    def test_unknown_sdk_fails_closed(self) -> None:
        data = manifest()
        data["dependencies"]["expo"] = "~55.0.0"
        self.assertTrue(any("no reviewed compatibility matrix" in error for error in validate(data)))

    def test_missing_or_invalid_dependencies_fail_closed(self) -> None:
        self.assertTrue(validate({}))
        data = manifest()
        del data["dependencies"]["react-native"]
        self.assertTrue(any("react-native" in error for error in validate(data)))

    def test_cli_handles_bad_json_and_bad_pairing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "package.json"
            path.write_text("{ broken", encoding="utf-8")
            self.assertEqual(main([str(path)]), 1)
            bad = manifest()
            bad["dependencies"]["react-native"] = "0.88.0"
            path.write_text(json.dumps(bad), encoding="utf-8")
            self.assertEqual(main([str(path)]), 1)
            path.write_text(json.dumps(manifest()), encoding="utf-8")
            self.assertEqual(main([str(path)]), 0)


if __name__ == "__main__":
    unittest.main()
