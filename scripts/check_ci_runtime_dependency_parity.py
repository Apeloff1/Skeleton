#!/usr/bin/env python3
"""Fail closed on stale dependency floors in the canonical CI validation lanes.

The source check deliberately needs only Python stdlib: it runs before the
Quarantine Policy job installs any project packages. Version changes must be
reviewed in the appropriate workflow and reflected in this list together.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS: dict[tuple[str, str], tuple[str, ...]] = {
    ("merge-readiness.yml", "Install focused unit-test runtime"): (
        "httpx>=0.28.1,<1", "fastapi>=0.142.2,<1", "pydantic>=2.14.1,<3",
        "pydantic-settings>=2.15.0,<3", "cryptography>=50.0.2",
    ),
    ("merge-readiness.yml", "Install focused quality dependencies"): (
        "ruff==0.17.2", "fastapi==0.161.1", "httpx>=0.28.1,<1",
        "pydantic-settings>=2.15.0,<3", "cryptography>=50.0.2",
    ),
    ("merge-readiness.yml", "Install focused test dependency"): (
        "httpx>=0.28.1,<1", "fastapi>=0.142.2,<1", "pydantic>=2.14.1,<3",
        "pydantic-settings>=2.15.0,<3", "cryptography>=50.0.2",
    ),
    ("backend-quality.yml", "Install full quality dependencies"): (
        "fastapi==0.161.1", "pydantic-settings>=2.15.0,<3", "httpx==0.28.1",
    ),
    ("backend-quality.yml", "Install plan-only quality runtime"): (
        "pydantic>=2.14.1,<3",
    ),
}


def validate_source(filename: str, source: str) -> list[str]:
    problems: list[str] = []
    for (target, step), expected in CHECKS.items():
        if target != filename:
            continue
        marker = "      - name: " + step + "\n"
        if source.count(marker) != 1:
            problems.append(f"{filename}: expected exactly one {step} install step")
            continue
        part = source.split(marker, 1)[1].split("\n      - ", 1)[0]
        if "run:" not in part:
            problems.append(f"{filename}: {step} has no executable installation command")
            continue
        actual = re.findall(r'"([^"\n]+)"', part)
        for requirement in expected:
            if actual.count(requirement) != 1:
                problems.append(
                    f"{filename}: {step} missing exact supported requirement {requirement}"
                )
    return problems


def validate(root: Path = ROOT) -> list[str]:
    issues: list[str] = []
    for filename in sorted({f for f, _ in CHECKS}):
        path = root / ".github" / "workflows" / filename
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            issues.append(f"{filename}: unreadable ({type(exc).__name__})")
            continue
        issues.extend(validate_source(filename, source))
    return issues


def main() -> int:
    issues = validate()
    for issue in issues:
        print("CI package floor contract failure:", issue)
    if not issues:
        print("CI unit, SAST, automation and backend quality floors verified")
    return int(bool(issues))


if __name__ == "__main__":
    raise SystemExit(main())
