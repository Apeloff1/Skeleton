from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AXIS_ID = "AC-09"
EXPECTED_MODES = (
    "clock_skew",
    "suspend_resume",
    "lease_fencing",
    "expiry_property",
)
NON_AUTHORITATIVE = True
CREATES_BINDING = False
ACCEPTS_RISK = False
LOWERS_SEVERITY = False
PROMOTES_MATURITY = False


def main() -> int:
    subprocess.run(
        ["python", "-m", "pytest", "-q",
         "skeleton/testing/test_adversarial_ac09_time_lease.py"],
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
