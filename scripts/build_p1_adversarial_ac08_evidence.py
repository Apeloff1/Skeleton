from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AXIS_ID = "AC-08"
EXPECTED_MODES = (
    "restore_drill",
    "tombstone_propagation",
    "external_reconciliation",
    "credential_revalidation",
)
NON_AUTHORITATIVE = True
CREATES_BINDING = False
ACCEPTS_RISK = False
LOWERS_SEVERITY = False
PROMOTES_MATURITY = False


def main() -> int:
    subprocess.run(
        ["python", "-m", "pytest", "-q",
         "skeleton/testing/test_adversarial_ac08_restore.py"],
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
