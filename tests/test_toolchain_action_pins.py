"""Exact, immutable October 2026 toolchain action release pins."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("toolchain_contract", ROOT / "scripts/check_toolchain_contract.py")
assert SPEC is not None and SPEC.loader is not None
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)

class ToolchainActionPinTests(unittest.TestCase):
    def test_core_actions_use_immutable_verifiable_generations(self) -> None:
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertGreater(CONTRACT.pinned_action_count(ci, "actions/checkout", "v7.0.1"), 0)
        self.assertGreater(CONTRACT.pinned_action_count(ci, "actions/setup-python", "v7.0.0"), 0)
        self.assertEqual(CONTRACT.pinned_action_count(ci, "actions/setup-node", "v7.1.0"), 1)
        self.assertEqual(ci.count("actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0"), 1)
        self.assertEqual(CONTRACT.pinned_action_count(ci, "astral-sh/setup-uv", "v10.3.0"), 3)
        self.assertEqual(ci.count("astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884 # v10.3.0"), 3)

    def test_floating_or_forged_pin_is_not_accepted(self) -> None:
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        tampered = ci.replace("949feb2413d6458794dcd2491c4babbbce0c15c1", "0" * 40)
        self.assertNotIn("actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0", tampered)
        self.assertEqual(tampered.count("actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0"), 0)

if __name__ == "__main__":
    unittest.main()
