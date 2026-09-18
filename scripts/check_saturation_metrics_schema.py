#!/usr/bin/env python3
"""Versioned fail-closed saturation-controller metrics schema (#969 S400).

Counts: runnable/blocked depth, active leases, capacity, queue/PR pressure,
completions, rejections. Unknown fields, negative numbers, and missing
evidence fail closed. Distinct from the S010 queue-trend schema.

Finding prefix: ``saturation-metrics``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_KEY = "reserve-S400-saturation-metrics"
CONFLICT_DOMAIN = "ops.spec.saturation_metrics"
INT_FIELDS: tuple[str, ...] = (
    "runnable_depth",
    "blocked_depth",
    "active_leases",
    "capacity",
    "queue_pressure",
    "pr_pressure",
    "completions",
    "rejections",
)
DOCUMENT_FIELDS = frozenset(("schema_version", "window", "evidence_refs", *INT_FIELDS))
_FINDING_PREFIX = "saturation-metrics"


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def validate_saturation_metrics(document: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [_error("unknown root_type", "saturation metrics document must be an object")]
    unknown = set(document) - DOCUMENT_FIELDS
    if unknown:
        errors.append(
            _error(
                "unknown field",
                "document has unknown fields: " + ", ".join(sorted(str(item) for item in unknown)),
            )
        )
    missing = DOCUMENT_FIELDS - set(document)
    if missing:
        errors.append(
            _error("missing_value field", "document missing fields: " + ", ".join(sorted(missing)))
        )
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(_error("unknown schema_version", f"schema_version must be exactly {SCHEMA_VERSION}"))
    window = document.get("window")
    if not isinstance(window, str) or not window.strip():
        errors.append(_error("missing_value window", "window must be a non-empty string"))
    for name in INT_FIELDS:
        if name not in document:
            continue
        value = document[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(_error("unknown count", f"{name} must be an integer >= 0"))
    refs = document.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        errors.append(_error("missing_value evidence_refs", "evidence_refs must be a non-empty list"))
        return errors
    for index, ref in enumerate(refs):
        if not isinstance(ref, str) or not ref.strip():
            errors.append(
                _error("unknown evidence_ref", f"evidence_refs[{index}] must be a non-empty string")
            )
    capacity = document.get("capacity")
    leases = document.get("active_leases")
    if isinstance(capacity, int) and not isinstance(capacity, bool) and isinstance(leases, int) and not isinstance(leases, bool):
        if leases > capacity:
            errors.append(_error("unknown lease_overflow", "active_leases must be <= capacity"))
    return errors


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
    parser.add_argument("path", type=Path, help="saturation-metrics JSON document")
    args = parser.parse_args(argv)
    errors = validate_saturation_metrics(load_document(args.path))
    if errors:
        print("Saturation-metrics schema validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"Saturation-metrics schema v{SCHEMA_VERSION} accepted {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
