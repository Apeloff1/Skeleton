#!/usr/bin/env python3
"""Validate fast-versus-specialized Actions without weakening required gates.

Standard library only: used by Backend Quality PR security/policy scanning.
Manual verification may be omitted on an iteration, but absence is NEVER
a passing release qualification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

SCHEMA = "skeleton.ci.workflow_tiers.v1"
ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = Path(".github/workflows")
INDEX = Path("machine/ci_workflow_tiers.json")


def events(source: str) -> set[str]:
    """Read top-level on: event names without resolving untrusted YAML tags."""
    lines = source.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line == "on:")
    except StopIteration as exc:
        raise ValueError("workflow missing multiline 'on:' trigger") from exc
    result: set[str] = set()
    for line in lines[start + 1:]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        match = re.match(r"^  ([a-z_]+):(?:\s*(?:#.*)?)?$", line)
        if match:
            result.add(match.group(1))
    return result


def audit(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    try:
        policy = json.loads((root / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        return [f"cannot read CI tier registry: {exc}"]
    if not isinstance(policy, dict) or policy.get("schema") != SCHEMA:
        return ["unrecognized CI tier registry schema"]
    specialised = policy.get("specialized_manual_only")
    core = policy.get("core_automatic_pr")
    if (not isinstance(specialised, list) or not isinstance(core, list)
            or not specialised or not core
            or any(not isinstance(p, str) or not p.endswith(".yml") or "/" in p
                   for p in specialised + core)):
        return ["CI tiers must be nonempty sets of plain .yml file names"]
    if len(set(specialised + core)) != len(specialised + core):
        return ["workflow cannot belong to multiple CI tiers"]
    rules = policy.get("release_rules")
    if not isinstance(rules, dict) or not rules or any(x is not True for x in rules.values()):
        failures.append("release rules must preserve non-compensable explicit verification")

    for path in specialised:
        try:
            source = (root / WORKFLOWS / path).read_text(encoding="utf-8")
            label = re.search(r"^name:\s*(.+?)\s*$", source, re.MULTILINE)
            if not label or "[Specialized]" not in label.group(1):
                failures.append(f"{path}: missing visible [Specialized] tag")
            found = events(source)
            if found != {"workflow_dispatch"}:
                failures.append(f"{path}: specialized workflow must be dispatch-only, got {sorted(found)}")
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(f"{path}: cannot validate specialist ({exc})")
    for path in core:
        try:
            found = events((root / WORKFLOWS / path).read_text(encoding="utf-8"))
            if "pull_request" not in found:
                failures.append(f"{path}: core required/security PR trigger removed")
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(f"{path}: cannot validate core ({exc})")
    # Keep the sole canonical required aggregate intact. Do not classify
    # its unrun or failed prerequisites as a success to make builds appear green.
    try:
        required = (root / WORKFLOWS / "merge-readiness.yml").read_text(encoding="utf-8")
        if "name: Merge Readiness" not in required or "result != \"success\"" not in required:
            failures.append("canonical Merge Readiness fails to reject non-success prerequisites")
    except (OSError, UnicodeError) as exc:
        failures.append(f"required aggregate missing ({exc})")
    try:
        backend = (root / WORKFLOWS / "backend-quality.yml").read_text(encoding="utf-8")
        for required in (
            "python scripts/check_ci_workflow_tiers.py",
            "python scripts/check_workflow_permissions.py",
            "python scripts/check_repository_python_sast.py",
            "python scripts/check_malware_iocs.py",
        ):
            if required not in backend:
                failures.append(f"Backend Quality lost required scan {required}")
        for specialist in (
            "Jeeves game development, fidelity and continuous production contracts",
            "Security, provider-chaos, and developer-tooling adversarial regression tests",
        ):
            if not re.search(
                r"^      - name: " + re.escape(specialist)
                + r"\n        if: .*github\.event_name == 'workflow_dispatch'",
                backend, re.MULTILINE,
            ):
                failures.append(f"Backend Quality must dispatch deep suite: {specialist}")
    except (OSError, UnicodeError) as exc:
        failures.append(f"Backend Quality missing ({exc})")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    problems = audit(args.root)
    for problem in problems:
        print("CI TIER ERROR:", problem)
    if problems:
        return 1
    print("CI tiers: fast PR plus explicit specialized qualifications verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
