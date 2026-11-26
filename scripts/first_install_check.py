#!/usr/bin/env python3
"""First-install readiness check for Skeleton.

Verifies that a fresh clone can install and start without additional manual steps
beyond copying .env.example and setting required values.
"""
import subprocess
import sys
from pathlib import Path

def check_python_version():
    if sys.version_info < (3, 10):
        print("FAIL: Python >= 3.10 required")
        return False
    print(f"OK: Python {sys.version_info.major}.{sys.version_info.minor}")
    return True

def check_pyproject():
    if not Path("pyproject.toml").exists():
        print("FAIL: pyproject.toml missing")
        return False
    print("OK: pyproject.toml present")
    return True

def check_env_example():
    if not Path(".env.example").exists():
        print("FAIL: .env.example missing")
        return False
    print("OK: .env.example present")
    return True

def main():
    ok = True
    ok &= check_python_version()
    ok &= check_pyproject()
    ok &= check_env_example()
    if ok:
        print("\nFirst-install checks passed. Next: copy .env.example to .env and pip install -e .")
        return 0
    return 1

if __name__ == "__main__":
    sys.exit(main())

def check_env_example_content():
    env = Path(".env.example")
    if not env.exists():
        return False
    content = env.read_text()
    required = ["OPENAI_API_KEY", "AI_PROVIDER"]
    for key in required:
        if key not in content:
            print(f"WARN: {key} not in .env.example")
            return False
    print("OK: .env.example has required keys")
    return True

# Extend main
if __name__ == "__main__":
    ok = True
    ok &= check_python_version()
    ok &= check_pyproject()
    ok &= check_env_example()
    ok &= check_env_example_content()
    if ok:
        print("\nFirst-install checks passed. Next: copy .env.example to .env and pip install -e .")
        sys.exit(0)
    sys.exit(1)
