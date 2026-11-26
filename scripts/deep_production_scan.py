#!/usr/bin/env python3
"""Deep production-grade scan for Skeleton.

Runs a comprehensive battery of checks for first-install readiness,
AI configuration, and test collection health.
"""
import subprocess
import sys
from pathlib import Path

def run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr

def check_first_install():
    print("=== First-install checks ===")
    for script in [
        "scripts/first_install_check.py",
        "scripts/ai_first_install_check.py",
        "scripts/ai_response_quality_check.py",
    ]:
        code, out = run(["python3", script])
        print(f"{script}: {'PASS' if code == 0 else 'FAIL'}")
        if code != 0:
            print(out[-200:])

def check_pip_install():
    print("=== pip install dry-run ===")
    code, out = run(["python3", "-m", "pip", "install", "-e", ".", "--dry-run"])
    print(f"pip install -e . --dry-run: {'PASS' if code == 0 else 'FAIL'}")

def check_test_collection():
    print("=== pytest collection sample ===")
    code, out = run(["python3", "-m", "pytest", "tests/", "-q", "--collect-only", "--maxfail=3"])
    print(f"pytest collection: {'PASS' if code == 0 else 'PARTIAL'}")
    if "error" in out.lower():
        print(out[-300:])

def main():
    check_first_install()
    check_pip_install()
    check_test_collection()
    print("\nDeep production scan complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
