from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_trace_pr_impact",
    ROOT / "scripts" / "check_trace_pr_impact.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TracePRImpactTests(unittest.TestCase):
    def test_trace_control_paths_are_explicit(self) -> None:
        self.assertTrue(
            MODULE._is_control_path("machine/requirement_registry.json")
        )
        self.assertTrue(
            MODULE._is_control_path("machine/traceability/DP-000-040.json")
        )
        self.assertFalse(MODULE._is_control_path("mystery/runtime.py"))

    def test_hex_object_id_validation(self) -> None:
        with self.assertRaisesRegex(MODULE.TraceImpactError, "hexadecimal"):
            MODULE._changed_files(ROOT, "not-a-sha", "0" * 40)


if __name__ == "__main__":
    unittest.main()
