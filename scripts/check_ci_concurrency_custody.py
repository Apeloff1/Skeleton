#!/usr/bin/env python3
"""Fail closed when core CI workflows can cancel an earlier main SHA run.

Main validation is provenance evidence. For pull requests, older checks may be
superseded only by a newer head of the *same PR*. This is a source contract;
it does not simulate GitHub Actions scheduling.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {
    "merge-readiness.yml": "merge-readiness",
    "backend-quality.yml": "backend-quality",
    "app-foundation-e2e.yml": "app-foundation-e2e",
}
EXPECTED_CANCEL = "$" + "{{ github.event_name == 'pull_request' }}"


def validate_text(name: str, content: str) -> list[str]:
    issues: list[str] = []
    prefix = WORKFLOWS.get(name)
    if prefix is None:
        return [f"{name}: unreviewed workflow"]
    block = re.search(r"(?m)^concurrency:[ \t]*\n((?:^[ \t]+[^\n]*\n?)*)", content)
    if block is None:
        return [f"{name}: missing global concurrency block"]
    data: dict[str, str] = {}
    for line in block.group(1).splitlines():
        key, sep, value = line.strip().partition(":")
        if sep and key in ("group", "cancel-in-progress"):
            if key in data:
                issues.append(f"{name}: duplicated {key}")
            data[key] = value.strip()
    expected_group = prefix + "-$" + "{{ github.event.pull_request.number || github.sha }}"
    if data.get("group") != expected_group:
        issues.append(f"{name}: main SHA/PR-number concurrency grouping drifted")
    if data.get("cancel-in-progress") != EXPECTED_CANCEL:
        issues.append(f"{name}: main SHA must not be cancelled by a newer push")
    return issues


def validate(root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    for file in WORKFLOWS:
        path = root / ".github" / "workflows" / file
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            problems.append(f"{file}: unreadable ({type(exc).__name__})")
            continue
        problems.extend(validate_text(file, content))
    return problems


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print("CI concurrency custody failure:", error)
        return 1
    print("CI concurrency custody OK: pull-request-only supersession, immutable main SHA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
