#!/usr/bin/env python3
"""Run bounded first-install preflight and test collection (not release proof)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS: tuple[tuple[str, tuple[str, ...], int], ...] = (
    ("first-install preflight", ("scripts/first_install_check.py",), 120),
    ("AI configuration preflight", ("scripts/ai_first_install_check.py",), 120),
    ("AI quality-gate inventory", ("scripts/ai_response_quality_check.py",), 120),
    ("package resolution dry run", ("-m", "pip", "install", "-e", ".", "--dry-run"), 300),
    ("pytest collection", ("-m", "pytest", "tests/", "-q", "--collect-only", "--maxfail=3"), 600),
)


def run_check(arguments: tuple[str, ...], timeout: int) -> tuple[bool, str]:
    """Do not copy subprocess output (which may contain credentials) into logs."""
    try:
        result = subprocess.run(
            [sys.executable, *arguments],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except OSError:
        return False, "process launch failed"
    return result.returncode == 0, f"exit {result.returncode}"


def main() -> int:
    passed = 0
    for name, arguments, timeout in CHECKS:
        ok, reason = run_check(arguments, timeout)
        passed += int(ok)
        print(f"{name}: {'PASS' if ok else 'FAIL'} ({reason})", flush=True)
    print(f"Preflight checks passed: {passed}/{len(CHECKS)}")
    print("No live inference, device, production recovery or release qualification implied.")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
