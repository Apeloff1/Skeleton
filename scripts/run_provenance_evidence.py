#!/usr/bin/env python3
"""Execute declared Python test evidence for canonical provenance records."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "docs" / "lineage" / "consolidation-manifest.v1.json"


def canonical_test_paths(payload: object) -> list[Path]:
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")

    components = payload.get("components")
    if not isinstance(components, list):
        raise ValueError("manifest components must be a list")

    selected: list[Path] = []
    seen: set[str] = set()
    for component in components:
        if not isinstance(component, dict) or component.get("canonical_status") != "canonical":
            continue

        component_id = str(component.get("id", "<unknown>"))
        evidence = component.get("evidence")
        if not isinstance(evidence, list):
            raise ValueError(f"{component_id}: evidence must be a list")

        executable = [
            str(path)
            for path in evidence
            if isinstance(path, str)
            and path.startswith("tests/")
            and path.endswith(".py")
        ]
        if not executable:
            raise ValueError(
                f"{component_id}: canonical passing status requires Python test evidence under tests/"
            )

        for relative in executable:
            if relative in seen:
                continue
            path = (REPO_ROOT / relative).resolve()
            if REPO_ROOT not in path.parents:
                raise ValueError(f"{component_id}: evidence escapes repository: {relative}")
            if not path.is_file():
                raise ValueError(f"{component_id}: evidence test does not exist: {relative}")
            seen.add(relative)
            selected.append(path)

    return selected


def main() -> int:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    try:
        tests = canonical_test_paths(payload)
    except ValueError as exc:
        print(f"provenance-evidence: rejected: {exc}", file=sys.stderr)
        return 1

    for path in tests:
        relative = path.relative_to(REPO_ROOT)
        print(f"provenance-evidence: running {relative}")
        completed = subprocess.run(
            [sys.executable, str(relative)],
            cwd=REPO_ROOT,
            check=False,
        )
        if completed.returncode != 0:
            print(
                f"provenance-evidence: failed {relative} with exit code {completed.returncode}",
                file=sys.stderr,
            )
            return completed.returncode

    print(f"provenance-evidence: OK ({len(tests)} canonical evidence test files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
