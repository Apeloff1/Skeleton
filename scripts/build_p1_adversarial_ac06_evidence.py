from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AXIS_ID = "AC-06"
EXPECTED_MODES = (
    "reconciliation_drill",
    "duplicate_delivery",
    "orphan_sweep",
    "projection_rebuild",
)
NON_AUTHORITATIVE = True
CREATES_BINDING = False
ACCEPTS_RISK = False
LOWERS_SEVERITY = False
PROMOTES_MATURITY = False


def main() -> int:
    subprocess.run(
        ["python", "-m", "pytest", "-q",
         "skeleton/testing/test_adversarial_ac06_reconciliation.py"],
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
