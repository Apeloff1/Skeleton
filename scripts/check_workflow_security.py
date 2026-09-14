#!/usr/bin/env python3
"""Fail closed on unsafe GitHub Actions workflow patterns.

Policy:
- third-party/marketplace/reusable actions must be pinned to a full 40-char SHA;
- checkout credentials may not be explicitly persisted;
- pull_request_target is forbidden because it combines base-repo secrets/tokens
  with attacker-controlled PR metadata unless designed with extreme care;
- write-all permissions are forbidden.

This intentionally uses text-level checks rather than YAML parsing so the gate
has no third-party dependencies and cannot be bypassed by YAML 1.1/1.2 parser
behavior differences.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")


def audit_workflow(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")

    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if re.match(r"^pull_request_target\s*:", stripped):
            problems.append(f"{path}:{lineno}: pull_request_target is forbidden")
        if re.search(r"\bwrite-all\b", stripped, flags=re.IGNORECASE):
            problems.append(f"{path}:{lineno}: write-all permissions are forbidden")
        if re.match(r"^persist-credentials\s*:\s*true\s*(?:#.*)?$", stripped, re.IGNORECASE):
            problems.append(f"{path}:{lineno}: checkout credentials must not be persisted")

        match = USES.match(raw)
        if not match:
            continue
        target = match.group(1).strip("'\"")
        if target.startswith("./"):
            continue
        if target.startswith("docker://"):
            # Docker actions need digest pinning, never mutable tags.
            if "@sha256:" not in target:
                problems.append(f"{path}:{lineno}: Docker action is not digest-pinned: {target}")
            continue
        if "@" not in target:
            problems.append(f"{path}:{lineno}: external action has no immutable ref: {target}")
            continue
        _action, ref = target.rsplit("@", 1)
        if not FULL_SHA.fullmatch(ref):
            problems.append(f"{path}:{lineno}: action ref must be a full commit SHA: {target}")

    return problems


def main() -> int:
    if not WORKFLOWS.is_dir():
        print(f"workflow directory not found: {WORKFLOWS}", file=sys.stderr)
        return 2

    problems: list[str] = []
    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    for path in files:
        problems.extend(audit_workflow(path))

    if problems:
        print("GitHub Actions security policy violations:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"workflow security policy: OK ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
