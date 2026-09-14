#!/usr/bin/env python3
"""Fail CI when external GitHub Actions are referenced by mutable refs.

Local actions (``uses: ./...``) and Docker image actions (``docker://...``) are
outside this policy. Every repository-backed external action must be pinned to
an immutable 40-character commit SHA. A trailing comment may document the
human-readable release tag, e.g. ``# v4``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

WORKFLOW_ROOT = Path(__file__).resolve().parents[1] / ".github" / "workflows"
USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def iter_external_uses(path: Path):
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = USES_RE.match(raw_line)
        if not match:
            continue
        target = match.group(1).strip('"\'')
        if target.startswith("./") or target.startswith("docker://"):
            continue
        yield line_number, target


def validate_target(target: str) -> str | None:
    if "@" not in target:
        return "external action reference has no @ref"
    action, ref = target.rsplit("@", 1)
    if not action or "/" not in action:
        return "external action repository is malformed"
    if not SHA_RE.fullmatch(ref):
        return "external action must be pinned to a 40-character commit SHA"
    return None


def scan_workflows(root: Path = WORKFLOW_ROOT) -> list[str]:
    violations: list[str] = []
    if not root.is_dir():
        return [f"workflow directory not found: {root}"]

    workflow_files = sorted([*root.glob("*.yml"), *root.glob("*.yaml")])
    if not workflow_files:
        return [f"no workflow files found under {root}"]

    for path in workflow_files:
        for line_number, target in iter_external_uses(path):
            error = validate_target(target)
            if error:
                relative = path.relative_to(root.parents[1])
                violations.append(f"{relative}:{line_number}: {error}: {target}")
    return violations


def main() -> int:
    violations = scan_workflows()
    if violations:
        print("GitHub Actions pinning policy violations:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1
    print("GitHub Actions pinning policy: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
