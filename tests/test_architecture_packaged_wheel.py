from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_architecture_packaged_wheel",
    ROOT / "scripts" / "check_architecture_packaged_wheel.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PackagedWheelTests(unittest.TestCase):
    def test_masterplan_and_probe_contract_is_present(self) -> None:
        # The expensive build/install/import execution runs as a registered architecture
        # validator in CI. This unit test protects the masterplan linkage and probe surface.
        layers = MODULE._load(ROOT, MODULE.LAYERS)
        master = MODULE._load(ROOT, MODULE.MASTER)
        volume = next(v for v in master["volumes"] if v["key"] == "VOL-053")
        self.assertIn("materialize packaged-wheel import test", volume["gaps"])
        binding = next(
            b for b in layers["masterplan_bindings"] if b["volume_ref"] == "VOL-053"
        )
        self.assertIn(
            "materialize packaged-wheel import test",
            binding["required_gap_texts"],
        )


if __name__ == "__main__":
    unittest.main()
