#!/usr/bin/env python3
"""Fail closed on unsafe GitHub Actions workflow patterns.

Policy:
- third-party/marketplace/reusable actions must be pinned to a full 40-char SHA;
- every actions/checkout step must explicitly set persist-credentials: false;
- pull_request_target is forbidden because it combines base-repo authority with
  attacker-controlled pull-request context unless designed with extreme care;
- write-all permissions are forbidden;
- Docker actions must use immutable sha256 digests.

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
USES = re.compile(r"^(?P<indent>\s*)-?\s*uses:\s*(?P<target>[^\s#]+)")
PULL_REQUEST_TARGET = re.compile(r"^[\"']?pull_request_target[\"']?\s*:", re.IGNORECASE)
PERSIST_FALSE = re.compile(r"^\s*persist-credentials\s*:\s*false\s*(?:#.*)?$", re.IGNORECASE)
PERSIST_TRUE = re.compile(r"^\s*persist-credentials\s*:\s*true\s*(?:#.*)?$", re.IGNORECASE)


def _checkout_disables_persisted_credentials(lines: list[str], index: int, step_indent: int) -> bool:
    """Return True only when the checkout step explicitly disables credentials."""
    for later in lines[index + 1 :]:
        if not later.strip() or later.lstrip().startswith("#"):
            continue

        indent = len(later) - len(later.lstrip())
        stripped = later.strip()

        # A new sequence item at the checkout step's indentation ends the step.
        if indent <= step_indent and stripped.startswith("-"):
            break
        if indent < step_indent:
            break
        if PERSIST_FALSE.match(later):
            return True
    return False


def audit_workflow(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    for index, raw in enumerate(lines):
        lineno = index + 1
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if PULL_REQUEST_TARGET.match(stripped):
            problems.append(f"{path}:{lineno}: pull_request_target is forbidden")
        if re.search(r"\bwrite-all\b", stripped, flags=re.IGNORECASE):
            problems.append(f"{path}:{lineno}: write-all permissions are forbidden")
        if PERSIST_TRUE.match(raw):
            problems.append(f"{path}:{lineno}: checkout credentials must not be persisted")

        match = USES.match(raw)
        if not match:
            continue

        target = match.group("target").strip("'\"")
        step_indent = len(match.group("indent"))

        if target.startswith("./"):
            continue
        if target.startswith("docker://"):
            if "@sha256:" not in target:
                problems.append(f"{path}:{lineno}: Docker action is not digest-pinned: {target}")
            continue
        if "@" not in target:
            problems.append(f"{path}:{lineno}: external action has no immutable ref: {target}")
            continue

        action, ref = target.rsplit("@", 1)
        if not FULL_SHA.fullmatch(ref):
            problems.append(f"{path}:{lineno}: action ref must be a full commit SHA: {target}")

        if action.lower() == "actions/checkout" and not _checkout_disables_persisted_credentials(
            lines, index, step_indent
        ):
            problems.append(
                f"{path}:{lineno}: actions/checkout must explicitly set persist-credentials: false"
            )

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
