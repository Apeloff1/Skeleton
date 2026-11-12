#!/usr/bin/env python3
"""Fail closed if targeted CI Python jobs omit archive-signature verification support.

Pytest's explicit plugin inventory imports the offline archive-signature suite
before executing the selected tests. Every job using that inventory must
install cryptography; removing the plugin is not a valid workaround.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github/workflows/ci.yml"
REQUIRED_JOBS = ("skeleton-test", "java-accelerators", "assembly-accelerators")
CRYPTO_REQUIREMENT = '"cryptography>=50.0.2,<51"'
JOB_LINE = re.compile(r"^  ([a-z][a-z0-9-]*):\s*$", re.MULTILINE)


def validate(source: str) -> list[str]:
    """Check the exact install stanza within each Python testing job."""
    boundaries = list(JOB_LINE.finditer(source))
    jobs = {
        match.group(1): source[match.end():boundaries[i + 1].start() if i + 1 < len(boundaries) else len(source)]
        for i, match in enumerate(boundaries)
    }
    errors: list[str] = []
    for name in REQUIRED_JOBS:
        block = jobs.get(name)
        if block is None:
            errors.append(f"{name}: CI job absent")
            continue
        if "python -m pip install" not in block or CRYPTO_REQUIREMENT not in block:
            errors.append(f"{name}: bounded cryptography install missing")
    return errors


def main() -> int:
    errors = validate(CI.read_text(encoding="utf-8"))
    if errors:
        for error in errors:
            print(error)
        return 1
    print("CI Python signing dependencies: OK (3 job installation slices)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
