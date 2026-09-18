#!/usr/bin/env python3
"""Fail-closed named-task reconciler for issues #929–#956 (#969 S492).

Fixture-driven classifier of ownership, status, supersedence, and merge
state. Each named task is exactly one of:

* current — live target; keep it, do not open a second PR
* superseded — stale named target; list it under ``retire`` in the report
* merged — implementing change already landed
* unknown — missing, contradictory, or unclassified evidence (gate failure)

Unknown always fails closed. Living PR numbers are echoed as
``do_not_duplicate`` so callers do not clone an open PR. Retirement is
report-only: this module never comments, closes, or opens GitHub objects.

Conflict domain: ``ops.readonly.named_reconcile``. Finding prefix:
``named-reconcile``. Stdlib only. No network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_ID = "reserve-S492-named-task-reconcile"
CONFLICT_DOMAIN = "ops.readonly.named_reconcile"
ISSUE_RANGE_START = 929
ISSUE_RANGE_END = 956
CLASSES: tuple[str, ...] = ("current", "superseded", "merged", "unknown")
CLASS_SET = frozenset(CLASSES)
DOCUMENT_FIELDS = frozenset({"schema_version", "tasks"})
TASK_FIELDS = frozenset(
    {
        "issue",
        "title",
        "owner",
        "status",
        "kind",
        "merge_state",
        "superseded_by",
        "living_pr",
        "evidence_refs",
    }
)
STATUSES = frozenset({"open", "closed"})
KINDS = frozenset({"issue", "pull"})
MERGE_STATES = frozenset({"merged", "unmerged", "not_applicable"})
_FINDING_PREFIX = "named-reconcile"


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _norm(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower().replace("-", "_")
    return text or None


def _positive_int(value: object) -> int | None:
    if not _is_int(value) or value <= 0:
        return None
    return value


def classify_named_task(task: object) -> str:
    """Return exactly one closed class. Ambiguity fails closed as unknown."""

    if not isinstance(task, Mapping):
        return "unknown"
    if set(task) - TASK_FIELDS:
        return "unknown"
    if TASK_FIELDS - set(task):
        return "unknown"

    issue = task.get("issue")
    if not _is_int(issue) or issue < ISSUE_RANGE_START or issue > ISSUE_RANGE_END:
        return "unknown"

    title = task.get("title")
    if not isinstance(title, str) or not title.strip():
        return "unknown"

    owner = task.get("owner")
    if owner is not None and (not isinstance(owner, str) or not owner.strip()):
        return "unknown"

    status = _norm(task.get("status"))
    if status not in STATUSES:
        return "unknown"

    kind = _norm(task.get("kind"))
    if kind not in KINDS:
        return "unknown"

    merge_state = _norm(task.get("merge_state"))
    if merge_state not in MERGE_STATES:
        return "unknown"
    if kind == "pull" and merge_state == "not_applicable":
        return "unknown"

    superseded_by = task.get("superseded_by")
    if superseded_by is not None:
        replacement = _positive_int(superseded_by)
        if replacement is None or replacement == issue:
            return "unknown"

    living_pr = task.get("living_pr")
    if living_pr is not None and _positive_int(living_pr) is None:
        return "unknown"

    refs = task.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        return "unknown"
    if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
        return "unknown"

    if merge_state == "merged" and (status == "open" or living_pr is not None):
        return "unknown"

    if superseded_by is not None:
        return "superseded"
    if merge_state == "merged":
        return "merged"
    if status == "open":
        return "current"
    return "unknown"


def _row_for(index: int, task: object, klass: str) -> dict[str, object]:
    issue = task.get("issue") if isinstance(task, Mapping) else None
    owner = task.get("owner") if isinstance(task, Mapping) else None
    living_pr = task.get("living_pr") if isinstance(task, Mapping) else None
    superseded_by = task.get("superseded_by") if isinstance(task, Mapping) else None
    return {
        "index": index,
        "issue": issue if _is_int(issue) else None,
        "class": klass,
        "owner": owner if isinstance(owner, str) and owner.strip() else None,
        "living_pr": living_pr if _positive_int(living_pr) is not None else None,
        "superseded_by": superseded_by if _positive_int(superseded_by) is not None else None,
    }


def build_report(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Machine-readable reconcile packet. Retirement is report-only."""

    counts = {name: 0 for name in CLASSES}
    retire: list[int] = []
    do_not_duplicate: list[int] = []
    seen_living: set[int] = set()
    for row in rows:
        klass = str(row.get("class"))
        if klass in counts:
            counts[klass] += 1
        issue = row.get("issue")
        if klass == "superseded" and _is_int(issue):
            retire.append(issue)
        living_pr = row.get("living_pr")
        if klass in {"current", "superseded"} and _is_int(living_pr) and living_pr not in seen_living:
            seen_living.add(living_pr)
            do_not_duplicate.append(living_pr)
    retire.sort()
    do_not_duplicate.sort()
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "conflict_domain": CONFLICT_DOMAIN,
        "issue_range": [ISSUE_RANGE_START, ISSUE_RANGE_END],
        "counts": counts,
        "retire": retire,
        "do_not_duplicate": do_not_duplicate,
        "rows": list(rows),
    }


def reconcile_named_tasks(document: object) -> tuple[list[dict[str, object]], list[str]]:
    """Classify a fixture document. Unknown rows always append a violation."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [], [_error("unknown root_type", "named-task document must be an object")]

    extra = set(document) - DOCUMENT_FIELDS
    if extra:
        errors.append(
            _error(
                "unknown field",
                "document has unknown fields: " + ", ".join(sorted(str(item) for item in extra)),
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
        errors.append(_error("unknown schema_version", f"schema_version must be exactly {SCHEMA_VERSION}"))

    tasks = document.get("tasks")
    if not isinstance(tasks, list):
        errors.append(_error("unknown tasks_type", "tasks must be a list"))
        return [], errors

    rows: list[dict[str, object]] = []
    seen: dict[int, int] = {}
    for index, task in enumerate(tasks):
        klass = classify_named_task(task)
        row = _row_for(index, task, klass)
        rows.append(row)
        issue = row["issue"]
        if _is_int(issue):
            if issue in seen:
                errors.append(
                    _error(
                        "unknown duplicate",
                        f"issue {issue} appears at tasks[{seen[issue]}] and tasks[{index}]",
                    )
                )
            else:
                seen[issue] = index
        if klass == "unknown":
            errors.append(
                _error("unknown unclassified", f"tasks[{index}] issue={issue!r}")
            )

    expected = set(range(ISSUE_RANGE_START, ISSUE_RANGE_END + 1))
    present = set(seen)
    absent = sorted(expected - present)
    if absent:
        errors.append(
            _error(
                "missing_value issue",
                "missing named tasks in #929–#956: " + ", ".join(f"#{item}" for item in absent),
            )
        )
    return rows, errors


def load_document(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(_error("unreadable missing_doc", f"{path} is missing")) from exc
    except OSError as exc:
        raise SystemExit(_error("unreadable io_error", f"cannot read {path}: {type(exc).__name__}")) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            _error("unreadable json", f"invalid JSON in {path} at line {exc.lineno}, column {exc.colno}")
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="JSON fixture of issues #929–#956")
    args = parser.parse_args(argv)
    rows, errors = reconcile_named_tasks(load_document(args.path))
    report = build_report(rows)
    counts = report["counts"]
    assert isinstance(counts, dict)
    print(
        "Named-task reconcile: "
        + ", ".join(f"{name}={counts[name]}" for name in CLASSES)
    )
    retire = report["retire"]
    living = report["do_not_duplicate"]
    print("retire: " + (", ".join(f"#{item}" for item in retire) if retire else "(none)"))
    print(
        "do_not_duplicate: "
        + (", ".join(f"#{item}" for item in living) if living else "(none)")
    )
    if errors:
        print("Named-task reconcile failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
