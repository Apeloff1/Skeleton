#!/usr/bin/env python3
"""Validate the small active CI set against archived specialized qualifications.

Archive files deliberately do not run on GitHub Actions; restoring an archived
workflow to .github/workflows is a separate reviewed operation.
"""
from __future__ import annotations

import argparse
import json
import errno
import os
from pathlib import Path
import re
import stat

SCHEMA = "skeleton.ci.workflow_tiers.v1"
ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = Path(".github/workflows")
ARCHIVE = Path(".github/workflows-archive")
INDEX = Path("machine/ci_workflow_tiers.json")
# Explicit event-subscriber inventory: no extra independent Actions admission.
MAX_INDEPENDENT_WORKFLOWS = 24


def _unique_policy_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate registry keys rather than silently trusting the last value."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate CI registry key: {key}")
        result[key] = value
    return result


def _read_reviewed(root: Path, relative: Path) -> str:
    """Read only regular files beneath descriptor-anchored, unlinked directories.

    Checking Path.is_symlink() before Path.open() leaves a replacement window.
    Each component is instead opened relative to its already-open parent with
    O_NOFOLLOW, so a concurrent rename cannot redirect a reviewed evidence read.
    """
    if (relative.is_absolute() or not relative.parts
            or any(part in ("", ".", "..") for part in relative.parts)):
        raise ValueError(f"invalid CI evidence path: {relative}")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("descriptor-anchored CI evidence reads unsupported")
    limit = 1024 * 1024
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(root, directory_flags))
        for component in relative.parts[:-1]:
            descriptors.append(os.open(component, directory_flags, dir_fd=descriptors[-1]))
        fd = os.open(relative.parts[-1], file_flags, dir_fd=descriptors[-1])
        descriptors.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"CI evidence must be a regular file: {relative}")
        if info.st_nlink != 1:
            raise ValueError(f"CI evidence must not have hardlink aliases: {relative}")
        if info.st_size > limit:
            raise ValueError(f"oversized CI evidence file: {relative}")
        with os.fdopen(os.dup(fd), "rb") as stream:
            payload = stream.read(limit + 1)
        if len(payload) > limit:
            raise ValueError(f"oversized CI evidence file: {relative}")
        return payload.decode("utf-8")
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise ValueError(f"linked CI evidence path or invalid directory: {relative}") from exc
        raise
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def events(source: str) -> set[str]:
    """Read top-level YAML on: keys, without resolving untrusted YAML tags."""
    lines = source.splitlines()
    # A second top-level trigger, including inline or whitespace-suffixed
    # syntax, must not hide behind the single reviewed multiline block.
    # YAML permits several spellings that would otherwise escape exact matching.
    candidates = [
        (i, line) for i, line in enumerate(lines)
        if re.match(r"^on\s*:", line)
    ]
    starts = [i for i, line in candidates if line == "on:"]
    if len(candidates) != 1 or len(starts) != 1:
        raise ValueError("workflow requires exactly one literal multiline 'on:' trigger")
    found: set[str] = set()
    for line in lines[starts[0] + 1:]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        match = re.match(r"^  ([a-z_]+):(?:\s*(?:#.*)?)?$", line)
        if match:
            event = match.group(1)
            if event in found:
                raise ValueError("duplicate workflow trigger event")
            found.add(event)
        elif re.match(r"^  \S", line) and not line.lstrip().startswith("#"):
            # Do not silently miss inline, aliased, or quoted triggers.
            raise ValueError("unsupported workflow trigger event declaration")
    if not found:
        raise ValueError("workflow has no explicit trigger events")
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
        policy = json.loads(_read_reviewed(root, INDEX), object_pairs_hook=_unique_policy_pairs)
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
    names = specialised + core + reusable
    if len(set(names)) != len(names):
        return ["workflow cannot belong to multiple CI tiers"]
    approved = policy.get("automatic_event_workflows")
    if (not isinstance(approved, list) or not approved
            or any(type(name) is not str or not name.endswith((".yml", ".yaml"))
                   or "/" in name or name.startswith(".") for name in approved)
            or len(approved) != len(set(approved))
            or len(approved) > MAX_INDEPENDENT_WORKFLOWS):
        return ["invalid explicit automatic workflow inventory"]
    profiles = policy.get("automatic_event_triggers")
    if (not isinstance(profiles, dict) or set(profiles) != set(approved)
            or any(not isinstance(event_names, list) or not event_names
                   or any(type(event) is not str
                          or not re.fullmatch(r"[a-z_]+", event) for event in event_names)
                   or len(set(event_names)) != len(event_names)
                   or not independently_triggered(set(event_names))
                   for event_names in profiles.values())):
        return ["invalid explicit automatic event trigger profiles"]
    rules = policy.get("release_rules")
    if not isinstance(rules, dict) or not rules or any(x is not True for x in rules.values()):
        failures.append("release rules must preserve explicit qualification")
    active = sorted((root / WORKFLOWS).glob("*.yml"))
    active += sorted((root / WORKFLOWS).glob("*.yaml"))
    if not active:
        failures.append("unexpected active workflow count: 0")
    # Signed evidence workflows may sit beside the compact PR set when they
    # cannot run automatically. Only non-manual triggers consume the cap.
    automatic = 0
    automatic_files: set[str] = set()
    for path in active:
        # GitHub checks out symlinks as filesystem links. Never let an
        # admission audit read a workflow outside its reviewed source tree.
        # A linked workflow is also not a stable, independently reviewed gate.
        if path.is_symlink():
            failures.append(f"{path.name}: active workflow must not be a symlink")
            continue
        try:
            found = events(_read_reviewed(root, path.relative_to(root)))
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(
                f"{path.name}: cannot inspect active workflow ({exc})"
            )
            continue
        if independently_triggered(found):
            automatic += 1
            automatic_files.add(path.name)
            if path.name in profiles and found != set(profiles[path.name]):
                failures.append(
                    f"{path.name}: event admission trigger drift "
                    f"(expected={sorted(profiles[path.name])}, got={sorted(found)})"
                )
    if automatic > MAX_INDEPENDENT_WORKFLOWS:
        failures.append(f"unexpected active workflow count: {automatic}")
    # Numeric caps alone admit unauthorized replacement beneath the ceiling.
    # Both new automatic subscribers and missing expected gates fail closed.
    unregistered = sorted(automatic_files - set(approved))
    missing = sorted(set(approved) - automatic_files)
    if unregistered:
        failures.append(f"unregistered automatic workflows: {unregistered}")
    if missing:
        failures.append(f"expected automatic workflows not triggered: {missing}")
    for name in specialised:
        path = root / ARCHIVE / name
        if (root / WORKFLOWS / name).exists():
            failures.append(f"{name}: specialist unexpectedly active")
        try:
            source = _read_reviewed(root, ARCHIVE / name)
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
            found = events(_read_reviewed(root, WORKFLOWS / name))
            if found != {"workflow_call", "workflow_dispatch"}:
                failures.append(
                    f"{name}: required reusable workflow must be callable and manually dispatchable, "
                    f"without standalone push/PR triggers; got {sorted(found)}"
                )
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(f"{name}: cannot inspect required reusable workflow ({exc})")
        try:
            archived = _read_reviewed(root, ARCHIVE / name)
            if events(archived) != {"workflow_dispatch"}:
                failures.append(f"{name}: archived predecessor must remain dispatch-only")
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(f"{name}: missing archived reusable predecessor ({exc})")
    for name in core:
        try:
            found = events(_read_reviewed(root, WORKFLOWS / name))
            if "pull_request" not in found:
                failures.append(f"{name}: core PR trigger missing")
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(f"{name}: cannot inspect active gate ({exc})")
    try:
        readiness = _read_reviewed(root, WORKFLOWS / "merge-readiness.yml")
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
        backend = _read_reviewed(root, WORKFLOWS / "backend-quality.yml")
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
