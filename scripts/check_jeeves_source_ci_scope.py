#!/usr/bin/env python3
"""Bounded, fail-closed PR merge-tree scope for the existing Jeeves source gates.

All four qualifications retain their reviewed path patterns in one registry.
No source path, branch name or PR payload is interpolated into a shell command.
The caller must fail if scope evidence is unavailable, never silently skip.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("machine/jeeves_source_ci_trigger_registry.json")
SCHEMA = "skeleton.ci.jeeves_source_gate_scope.v1"
GATES = ("sealed", "integrated", "sqlite", "laptop")
_MAX_REGISTRY_BYTES = 64 * 1024
_MAX_DIFF_BYTES = 16 * 1024 * 1024
_MAX_CHANGED_PATHS = 100_000
_ALLOWED_PATTERN = re.compile(r"[A-Za-z0-9_./*-]{1,256}\Z")


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate source-gate registry member")
        result[key] = value
    return result


def _safe_path(value: str) -> bool:
    return (
        type(value) is str
        and bool(_ALLOWED_PATTERN.fullmatch(value))
        and not value.startswith("/")
        and "//" not in value
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def load_registry(root: Path = ROOT) -> dict[str, tuple[str, ...]]:
    path = root / REGISTRY
    if path.is_symlink():
        raise ValueError("source-gate registry cannot be a symlink")
    raw = path.read_bytes()
    if len(raw) > _MAX_REGISTRY_BYTES:
        raise ValueError("source-gate registry exceeds byte budget")
    data = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_no_duplicate_keys)
    if (type(data) is not dict
            or set(data) != {"schema", "gates"}
            or data["schema"] != SCHEMA
            or type(data["gates"]) is not dict
            or set(data["gates"]) != set(GATES)):
        raise ValueError("unrecognized source-gate registry contract")
    checked: dict[str, tuple[str, ...]] = {}
    for gate in GATES:
        entries = data["gates"][gate]
        if (type(entries) is not list
                or not 1 <= len(entries) <= 128
                or any(not _safe_path(entry) for entry in entries)
                or len(set(entries)) != len(entries)):
            raise ValueError("unsafe or ambiguous source-gate path patterns")
        checked[gate] = tuple(entries)
    return checked


def changed_paths(root: Path = ROOT) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "diff", "--no-renames", "--name-only", "-z", "HEAD^1", "HEAD", "--"],
        cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=45, shell=False,
    )
    raw = result.stdout
    if not raw or len(raw) > _MAX_DIFF_BYTES or not raw.endswith(b"\x00"):
        raise ValueError("missing or unbounded exact-head Git diff")
    paths = raw[:-1].decode("utf-8", "strict").split("\x00")
    if (len(paths) > _MAX_CHANGED_PATHS
            or any(not _safe_path(path) for path in paths)
            or len(set(paths)) != len(paths)):
        raise ValueError("unsafe exact-head Git diff paths")
    return tuple(paths)


def selected_gates(
    changes: tuple[str, ...] | list[str],
    registry: dict[str, tuple[str, ...]],
) -> dict[str, bool]:
    if not changes or any(not _safe_path(path) for path in changes):
        raise ValueError("unqualified exact-head source paths")
    if set(registry) != set(GATES):
        raise ValueError("source-gate registry incomplete")
    return {
        gate: any(
            fnmatchcase(path, pattern)
            for path in changes
            for pattern in registry[gate]
        )
        for gate in GATES
    }


def main() -> int:
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        raise ValueError("source qualification admission requires a pull_request merge ref")
    output = os.environ.get("GITHUB_OUTPUT")
    if not output or not Path(output).is_absolute():
        raise ValueError("missing runner-owned output channel")
    registry = load_registry()
    selected = selected_gates(changed_paths(), registry)
    payload = "".join(
        f"{gate}={'true' if selected[gate] else 'false'}\n" for gate in GATES
    )
    with Path(output).open("a", encoding="utf-8") as stream:
        stream.write(payload)
    print("Jeeves qualification scope: exact PR merge-tree paths classified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
