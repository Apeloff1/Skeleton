#!/usr/bin/env python3
"""Require canonical human/agent provenance for build-affecting handoffs.

The existing repo-intel note gate proves that a build-affecting change leaves a
handoff note. This checker proves that at least one changed handoff note also names
a canonical actor from repo-intel/contributors.json. Older/free-form notes without
an Author/agent field remain readable, but an explicitly populated unknown actor is
fail-closed so new bots/models cannot silently enter the repository provenance map.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import repo_intel as base  # noqa: E402
import repo_intel_contributions as contributions  # noqa: E402

AUTHOR_RE = re.compile(
    r"^\s*-?\s*\*\*Author/agent:\*\*\s*(.*?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
PLACEHOLDERS = {"", "-", "n/a", "none", "tbd", "unknown", "author/agent"}


def _read(path: str) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _build_surface(base_ref: str) -> tuple[list[str], list[str], list[str]]:
    cfg = base.load_json("config.json")
    changed = base.changed_paths(base_ref)
    impact = [
        path
        for path in changed
        if any(
            path == prefix.rstrip("/") or path.startswith(prefix)
            for prefix in cfg["build_affecting_prefixes"]
        )
        and not path.startswith("repo-intel/notes/")
    ]
    notes = [
        path
        for path in changed
        if path.startswith("repo-intel/notes/")
        and path.endswith(".md")
        and not path.endswith("/TEMPLATE.md")
    ]
    return changed, impact, notes


def validate_note(path: str) -> tuple[list[str], list[str]]:
    registry = contributions._registry()
    actors, exact = contributions._actor_maps(registry)
    values = [match.group(1).strip() for match in AUTHOR_RE.finditer(_read(path))]
    resolved: set[str] = set()
    invalid: list[str] = []
    for value in values:
        if value.casefold() in PLACEHOLDERS:
            continue
        actor_ids = contributions._declared_actor_ids(value, actors, exact)
        if actor_ids:
            resolved.update(actor_ids)
        else:
            invalid.append(value)
    return sorted(resolved), invalid


def gate(base_ref: str) -> int:
    contributions.check_contracts()
    _changed, impact, notes = _build_surface(base_ref)
    if not impact:
        print("repo-intel-contribution-gate: no build-affecting paths to gate")
        return 0
    if not notes:
        print("repo-intel-contribution-gate: ERROR: build-affecting changes require a changed handoff note", file=sys.stderr)
        return 1

    valid: list[tuple[str, list[str]]] = []
    invalid: list[tuple[str, list[str]]] = []
    missing: list[str] = []
    for path in notes:
        resolved, unknown = validate_note(path)
        if unknown:
            invalid.append((path, unknown))
        if resolved:
            valid.append((path, resolved))
        else:
            missing.append(path)

    if invalid:
        print("repo-intel-contribution-gate: ERROR: unregistered Author/agent values:", file=sys.stderr)
        for path, values in invalid:
            print(f"  - {path}: {', '.join(values)}", file=sys.stderr)
        print("Register the actor in repo-intel/contributors.json or use a canonical actor ID/alias.", file=sys.stderr)
        return 1

    if not valid:
        print(
            "repo-intel-contribution-gate: ERROR: at least one changed handoff note must contain "
            "**Author/agent:** with a canonical actor from repo-intel/contributors.json",
            file=sys.stderr,
        )
        for path in missing:
            print(f"  - missing canonical provenance: {path}", file=sys.stderr)
        return 1

    actors = sorted({actor for _path, actor_ids in valid for actor in actor_ids})
    print(
        "repo-intel-contribution-gate: passed "
        f"({len(impact)} build paths, {len(notes)} changed notes, actors={','.join(actors)})"
    )
    if missing:
        print(
            "repo-intel-contribution-gate: legacy/free-form changed notes without canonical provenance: "
            + ", ".join(missing)
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args(argv)
    return gate(args.base)


if __name__ == "__main__":
    raise SystemExit(main())
