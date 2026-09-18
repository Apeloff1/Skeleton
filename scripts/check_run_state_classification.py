#!/usr/bin/env python3
"""Fail-closed GitHub Actions run-state classifier (#969 S002).

Groups queued/cancelled/timed-out/failing runs as retryable, stale,
superseded, authoritative_failure, or unknown. Success completes as
``complete``. Unknown status/conclusion combinations fail closed.

This module classifies JSON only. It has no rerun, cancel, or mutation
authority. Finding prefix: ``run-state``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_KEY = "reserve-S002-run-state-classification"
CONFLICT_DOMAIN = "ci.readonly.run_classification"
CLASSES: tuple[str, ...] = (
    "retryable",
    "stale",
    "superseded",
    "authoritative_failure",
    "complete",
    "unknown",
)
CLASS_SET = frozenset(CLASSES)
KNOWN_STATUSES = frozenset(
    {
        "queued",
        "in_progress",
        "completed",
        "waiting",
        "requested",
        "pending",
        "waiting_for_review",
        "action_required",
    }
)
KNOWN_CONCLUSIONS = frozenset(
    {
        "success",
        "failure",
        "cancelled",
        "canceled",
        "timed_out",
        "skipped",
        "startup_failure",
        "action_required",
        "stale",
        "neutral",
    }
)
_FINDING_PREFIX = "run-state"
RUN_FIELDS = frozenset(
    {"status", "conclusion", "head_sha", "replaced_by", "newer_run", "html_url", "id"}
)


def _norm(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower().replace("-", "_")
    return text or None


def classify_run(run: object, *, current_sha: str | None = None) -> str:
    """Return exactly one closed class. Unknown combinations fail closed."""

    if not isinstance(run, Mapping):
        return "unknown"
    unknown_fields = set(run) - RUN_FIELDS
    if unknown_fields:
        return "unknown"
    status = _norm(run.get("status"))
    if status is None or status not in KNOWN_STATUSES:
        return "unknown"
    conclusion = run.get("conclusion")
    conc = _norm(conclusion) if conclusion is not None else None
    if conc == "canceled":
        conc = "cancelled"
    if conclusion is not None and conc not in KNOWN_CONCLUSIONS:
        return "unknown"

    head_sha = run.get("head_sha")
    current = current_sha.strip() if isinstance(current_sha, str) and current_sha.strip() else None
    if (
        current
        and isinstance(head_sha, str)
        and head_sha.strip()
        and head_sha.strip() != current
    ):
        if status in {"queued", "in_progress", "waiting", "requested", "pending"}:
            return "superseded"
        if conc in {"cancelled", "failure", "timed_out", "startup_failure", "skipped"}:
            return "superseded"

    if run.get("replaced_by") not in (None, "", False):
        return "superseded"

    if status in {"queued", "waiting", "requested", "pending", "in_progress", "waiting_for_review", "action_required"}:
        return "retryable"

    if status != "completed":
        return "unknown"
    if conc is None:
        return "unknown"
    if conc == "success":
        return "complete"
    if conc in {"skipped", "stale", "neutral"}:
        return "stale"
    if conc == "cancelled":
        if run.get("newer_run") is True:
            return "stale"
        if run.get("newer_run") not in (None, False):
            return "unknown"
        return "retryable"
    if conc in {"timed_out", "startup_failure"}:
        return "retryable"
    if conc == "failure":
        return "authoritative_failure"
    if conc == "action_required":
        return "retryable"
    return "unknown"


def classify_document(document: object) -> tuple[list[dict[str, object]], list[str]]:
    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [], [f"{_FINDING_PREFIX} unknown root_type: document must be an object"]
    version = document.get("schema_version")
    if version != SCHEMA_VERSION:
        errors.append(f"{_FINDING_PREFIX} unknown schema_version: must be exactly {SCHEMA_VERSION}")
    current_sha = document.get("current_sha")
    if current_sha is not None and not isinstance(current_sha, str):
        errors.append(f"{_FINDING_PREFIX} unknown current_sha: current_sha must be a string")
        current_sha = None
    runs = document.get("runs")
    if not isinstance(runs, list):
        errors.append(f"{_FINDING_PREFIX} unknown runs_type: runs must be a list")
        return [], errors
    rows: list[dict[str, object]] = []
    for index, run in enumerate(runs):
        klass = classify_run(run, current_sha=current_sha if isinstance(current_sha, str) else None)
        run_id = run.get("id") if isinstance(run, Mapping) else index
        rows.append({"index": index, "id": run_id, "class": klass})
        if klass == "unknown":
            errors.append(f"{_FINDING_PREFIX} unknown unclassified: runs[{index}] id={run_id!r}")
    return rows, errors


def load_document(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"{_FINDING_PREFIX} unreadable missing_doc: {path} is missing") from exc
    except OSError as exc:
        raise SystemExit(
            f"{_FINDING_PREFIX} unreadable io_error: cannot read {path}: {type(exc).__name__}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"{_FINDING_PREFIX} unreadable json: invalid JSON in {path} at line {exc.lineno}"
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="JSON document with schema_version, optional current_sha, runs")
    args = parser.parse_args(argv)
    rows, errors = classify_document(load_document(args.path))
    counts = {name: 0 for name in CLASSES}
    for row in rows:
        counts[str(row["class"])] += 1
    print(
        "Run-state classification: "
        + ", ".join(f"{name}={counts[name]}" for name in CLASSES)
    )
    if errors:
        print("Run-state classification failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
