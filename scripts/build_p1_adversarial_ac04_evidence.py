from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AXIS_ID = "AC-04"
EXPECTED_MODES = (
    "dependency_fault",
    "fallback_matrix",
    "policy_regression",
    "provider_outage",
)
NON_AUTHORITATIVE = True
CREATES_BINDING = False


def main() -> int:
    subprocess.run(
        ["python", "-m", "pytest", "-q", "skeleton/testing/test_adversarial_ac04_fallback.py"],
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
