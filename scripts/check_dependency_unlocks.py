#!/usr/bin/env python3
"""Fail-closed dependency unlock scan (#969 S491).

Classifies blocked tasks whose prerequisites have become validated/merged
in a fixture graph. Closed classes: still_blocked, unlocked, unknown.
Unknown status, missing prerequisites, extra fields, and unreadable
documents fail closed.

This module classifies JSON only. It has no issue, pull-request, or
repository mutation authority. Finding prefix: ``dependency-unlock``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path


SCHEMA_VERSION = 1
TASK_KEY = "reserve-S491-dependency-unlock-scan"
CONFLICT_DOMAIN = "ops.readonly.dependency_unlocks"
CLASSES: tuple[str, ...] = ("still_blocked", "unlocked", "unknown")
CLASS_SET = frozenset(CLASSES)
SATISFIED_STATUSES = frozenset({"validated", "merged"})
BLOCKING_STATUSES = frozenset(
    {
        "blocked",
        "queued",
        "assigned",
        "working",
        "rejected",
        "open",
    }
)
KNOWN_STATUSES = SATISFIED_STATUSES | BLOCKING_STATUSES
DOCUMENT_FIELDS = frozenset({"schema_version", "tasks"})
TASK_FIELDS = frozenset({"task_key", "status", "prerequisites"})
_FINDING_PREFIX = "dependency-unlock"


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _norm(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower().replace("-", "_")
    return text or None


def _task_key(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def parse_task(task: object) -> tuple[str | None, str | None, tuple[str, ...] | None]:
    """Return ``(task_key, status, prerequisites)`` or Nones when unreadable."""

    if not isinstance(task, Mapping):
        return None, None, None
    if set(task) - TASK_FIELDS:
        return None, None, None
    key = _task_key(task.get("task_key"))
    status = _norm(task.get("status"))
    raw_prereqs = task.get("prerequisites")
    if key is None or status not in KNOWN_STATUSES or not isinstance(raw_prereqs, list):
        return None, None, None
    prerequisites: list[str] = []
    for item in raw_prereqs:
        parsed = _task_key(item)
        if parsed is None:
            return None, None, None
        prerequisites.append(parsed)
    return key, status, tuple(prerequisites)


def classify_blocked_task(
    prerequisites: Sequence[str],
    nodes: Mapping[str, str | None],
) -> str:
    """Return one closed class for a readable blocked task.

    Direct prerequisites must all be present with a known status. Satisfied
    means validated or merged. Any missing, unreadable, or unknown
    prerequisite fails closed to ``unknown``.
    """

    if not prerequisites:
        return "unknown"
    remaining = False
    for dep in prerequisites:
        if dep not in nodes:
            return "unknown"
        status = nodes[dep]
        if status is None or status not in KNOWN_STATUSES:
            return "unknown"
        if status not in SATISFIED_STATUSES:
            remaining = True
    return "still_blocked" if remaining else "unlocked"


def classify_document(document: object) -> tuple[list[dict[str, object]], list[str]]:
    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [], [_error("unknown root_type", "document must be an object")]

    unknown_fields = set(document) - DOCUMENT_FIELDS
    if unknown_fields:
        errors.append(
            _error(
                "unknown field",
                "document has unknown fields: "
                + ", ".join(sorted(str(item) for item in unknown_fields)),
            )
        )
    missing = DOCUMENT_FIELDS - set(document)
    if missing:
        errors.append(
            _error(
                "missing_value field",
                "document missing fields: " + ", ".join(sorted(missing)),
            )
        )
    version = document.get("schema_version")
    if version != SCHEMA_VERSION:
        errors.append(
            _error("unknown schema_version", f"schema_version must be exactly {SCHEMA_VERSION}")
        )

    tasks = document.get("tasks")
    if not isinstance(tasks, list):
        errors.append(_error("unknown tasks_type", "tasks must be a list"))
        return [], errors

    parsed_rows: list[tuple[int, str | None, str | None, tuple[str, ...] | None]] = []
    nodes: dict[str, str | None] = {}
    seen: dict[str, int] = {}
    for index, task in enumerate(tasks):
        key, status, prerequisites = parse_task(task)
        parsed_rows.append((index, key, status, prerequisites))
        if key is None:
            continue
        if key in seen:
            errors.append(
                _error(
                    "unknown duplicate_task",
                    f"tasks[{index}] duplicates task_key {key!r} from tasks[{seen[key]}]",
                )
            )
            nodes[key] = None
            continue
        seen[key] = index
        nodes[key] = status

    rows: list[dict[str, object]] = []
    for index, key, status, prerequisites in parsed_rows:
        if status != "blocked":
            if key is None:
                errors.append(
                    _error("unknown unclassified", f"tasks[{index}] is unreadable")
                )
            continue
        klass = classify_blocked_task(prerequisites or (), nodes)
        rows.append({"index": index, "task_key": key, "class": klass})
        if klass == "unknown":
            errors.append(
                _error("unknown unclassified", f"tasks[{index}] task_key={key!r}")
            )
    return rows, errors


def load_document(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(_error("unreadable missing_doc", f"{path} is missing")) from exc
    except OSError as exc:
        raise SystemExit(
            _error("unreadable io_error", f"cannot read {path}: {type(exc).__name__}")
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            _error("unreadable json", f"invalid JSON in {path} at line {exc.lineno}")
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="fixture graph JSON with schema_version and tasks")
    args = parser.parse_args(argv)
    rows, errors = classify_document(load_document(args.path))
    counts = {name: 0 for name in CLASSES}
    grouped: dict[str, list[str]] = {name: [] for name in CLASSES}
    for row in rows:
        klass = str(row["class"])
        counts[klass] += 1
        grouped[klass].append(str(row["task_key"]))
    print(
        "Dependency unlock scan: " + ", ".join(f"{name}={counts[name]}" for name in CLASSES)
    )
    for name in ("unlocked", "still_blocked"):
        if grouped[name]:
            print(f"{name}: " + ", ".join(grouped[name]))
    if errors:
        print("Dependency unlock scan failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
