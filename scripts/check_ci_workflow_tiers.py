#!/usr/bin/env python3
"""Validate the small active CI set against archived specialized qualifications.

Archive files deliberately do not run on GitHub Actions; restoring an archived
workflow to .github/workflows is a separate reviewed operation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

SCHEMA = "skeleton.ci.workflow_tiers.v1"
ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = Path(".github/workflows")
ARCHIVE = Path(".github/workflows-archive")
INDEX = Path("machine/ci_workflow_tiers.json")

# One independently guarded queue-drain lane survives the owner-directed
# backlog pause. Housekeeping and three-hour expiry stay dispatch-only.
SCHEDULED_RECOVERY = frozenset({"queue-drain.yml"})
PAUSED_RECOVERY = frozenset({
    "actions-housekeeping-cli.yml",
    "three-hour-actions-queue-expiry.yml",
})


def events(source: str) -> set[str]:
    """Read top-level YAML on: keys, without resolving untrusted YAML tags."""
    lines = source.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line == "on:")
    except StopIteration as exc:
        raise ValueError("workflow missing multiline 'on:' trigger") from exc
    found: set[str] = set()
    for line in lines[start + 1:]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        match = re.match(r"^  ([a-z_]+):(?:\s*(?:#.*)?)?$", line)
        if match:
            found.add(match.group(1))
    return found


def independently_triggered(found: set[str]) -> bool:
    """Count only independent Actions admissions, not manually dispatched or called jobs.

    workflow_call never subscribes to repository events. Its caller consumes
    the existing PR workflow admission, while required native checks still run.
    """
    return bool(found - {"workflow_dispatch", "workflow_call"})


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
    reusable = policy.get("required_reusable_workflows")
    tiers = (specialised, core, reusable)
    if (any(not isinstance(group, list) or not group for group in tiers)
            or any(not isinstance(name, str) or not name.endswith(".yml") or "/" in name
                   for group in tiers for name in group)):
        return ["CI tiers require nonempty sets of plain .yml file names"]
    scheduled = policy.get("operational_scheduled_non_pr")
    paused = policy.get("operational_paused_manual_only")
    if (type(scheduled) is not list
            or len(scheduled) != len(SCHEDULED_RECOVERY)
            or any(type(name) is not str for name in scheduled)
            or set(scheduled) != SCHEDULED_RECOVERY):
        failures.append("scheduled operational registry must be the exact queue-drain lane")
        scheduled = []
    if (type(paused) is not list
            or len(paused) != len(PAUSED_RECOVERY)
            or any(type(name) is not str for name in paused)
            or set(paused) != PAUSED_RECOVERY):
        failures.append("paused operational registry must contain exactly two manual lanes")
        paused = []
    for name in SCHEDULED_RECOVERY | PAUSED_RECOVERY:
        if not (root / WORKFLOWS / name).is_file():
            failures.append(f"{name}: required operational workflow missing")
    names = specialised + core + reusable + scheduled + paused
    if len(set(names)) != len(names):
        return ["workflow cannot belong to multiple CI tiers"]
    rules = policy.get("release_rules")
    if not isinstance(rules, dict) or not rules or any(x is not True for x in rules.values()):
        failures.append("release rules must preserve explicit qualification")
    active = sorted((root / WORKFLOWS).glob("*.yml"))
    active += sorted((root / WORKFLOWS).glob("*.yaml"))
    if not active:
        failures.append("unexpected active workflow count: 0")
    # Count every independently triggered workflow except the one independently
    # guarded queue-drain recovery lane. All paused writers remain manual.
    automatic = 0
    for path in active:
        try:
            found = events(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(
                f"{path.name}: cannot inspect active workflow ({exc})"
            )
            continue
        if path.name == "queue-drain.yml":
            source = path.read_text(encoding="utf-8")
            if (found != {"workflow_dispatch", "schedule", "push"}
                    or not re.search(
                        r"(?m)^  push:\n    branches: \[main\]\n    paths: \['\.github/workflows/queue-drain\.yml'\]$", source
                    )
                    or not re.search(r"(?m)^permissions: \{\}$", source)):
                failures.append(f"{path.name}: operational-only trigger or permission drift")
            continue
        if path.name in PAUSED_RECOVERY:
            source = path.read_text(encoding="utf-8")
            if (found != {"workflow_dispatch"}
                    or not re.search(r"(?m)^permissions: \{\}$", source)):
                failures.append(f"{path.name}: paused workflow gained automatic admission or permissions")
            continue
        if independently_triggered(found):
            automatic += 1
    if automatic > 20:
        failures.append(f"unexpected active workflow count: {automatic}")
    for name in specialised:
        path = root / ARCHIVE / name
        if (root / WORKFLOWS / name).exists():
            failures.append(f"{name}: specialist unexpectedly active")
        try:
            source = path.read_text(encoding="utf-8")
            label = re.search(r"^name:\s*(.+?)\s*$", source, re.MULTILINE)
            if not label or "[Specialized]" not in label.group(1):
                failures.append(f"{name}: missing [Specialized] tag")
            found = events(source)
            if found != {"workflow_dispatch"}:
                failures.append(f"{name}: archived specialist must retain manual-only definition; got {sorted(found)}")
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(f"{name}: cannot inspect archived specialist ({exc})")
    for name in reusable:
        try:
            found = events((root / WORKFLOWS / name).read_text(encoding="utf-8"))
            if found != {"workflow_call", "workflow_dispatch"}:
                failures.append(
                    f"{name}: required reusable workflow must be callable and manually dispatchable, "
                    f"without standalone push/PR triggers; got {sorted(found)}"
                )
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(f"{name}: cannot inspect required reusable workflow ({exc})")
        try:
            archived = (root / ARCHIVE / name).read_text(encoding="utf-8")
            if events(archived) != {"workflow_dispatch"}:
                failures.append(f"{name}: archived predecessor must remain dispatch-only")
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(f"{name}: missing archived reusable predecessor ({exc})")
    for name in core:
        try:
            found = events((root / WORKFLOWS / name).read_text(encoding="utf-8"))
            if "pull_request" not in found:
                failures.append(f"{name}: core PR trigger missing")
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(f"{name}: cannot inspect active gate ({exc})")
    try:
        readiness = (root / WORKFLOWS / "merge-readiness.yml").read_text(encoding="utf-8")
        if ("name: Merge Readiness" not in readiness
                or "python -m compileall -q skeleton" not in readiness
                or "  pull_request:" not in readiness):
            failures.append("fast Merge Readiness smoke contract missing")
        for name in reusable:
            if f"uses: ./.github/workflows/{name}" not in readiness:
                failures.append(f"{name}: required reusable workflow not called by Merge Readiness")
    except (OSError, UnicodeError) as exc:
        failures.append(f"Merge Readiness missing ({exc})")
    try:
        backend = (root / WORKFLOWS / "backend-quality.yml").read_text(encoding="utf-8")
        # Backend Quality declares defaults.run.working-directory: backend.
        # Scanner commands are correctly relative to that working directory;
        # require the actual invocations rather than impossible backend/backend paths.
        for required in (
            "python scripts/check_ci_workflow_tiers.py",
            "python scripts/check_workflow_permissions.py",
            "python scripts/check_repository_python_sast.py",
            "python scripts/check_malware_iocs.py",
        ):
            if required not in backend:
                failures.append(f"Backend Quality missing scan: {required}")
        for name in (
            "Jeeves game development, fidelity and continuous production contracts",
            "Security, provider-chaos, and developer-tooling adversarial regression tests",
        ):
            if not re.search(
                r"^      - name: " + re.escape(name)
                + r"\n        if: .*github\.event_name == 'workflow_dispatch'",
                backend, re.MULTILINE,
            ):
                failures.append(f"Backend Quality must dispatch deep suite: {name}")
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
    print("CI tiers: compact active PR gates and offline archived specialists verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
