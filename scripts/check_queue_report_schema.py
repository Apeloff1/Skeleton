#!/usr/bin/env python3
"""Versioned fail-closed queue-trend schema (#969 S010).

Queue reports cover depth, age, cancellations, reruns, blockers, and avoided
fanout for one window. This is ops queue *trends*, not morning item
categories. Unknown fields, wrong types, negative counts, and missing evidence
fail closed. Unique prefix: ``queue-report``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
DOCUMENT_FIELDS = frozenset(
    {
        "schema_version",
        "window",
        "depth",
        "age_seconds",
        "cancellations",
        "reruns",
        "blockers",
        "avoided_fanout",
        "evidence_refs",
    }
)
COUNT_FIELDS = (
    "depth",
    "cancellations",
    "reruns",
    "blockers",
    "avoided_fanout",
)
_FINDING_PREFIX = "queue-report"


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_nonneg_int(field: str, value: object, errors: list[str]) -> None:
    if not _is_int(value):
        errors.append(_error("unknown type", f"{field} must be an integer >= 0"))
        return
    if value < 0:
        errors.append(_error("unknown negative", f"{field} must be >= 0"))


def validate_queue_report(document: object) -> list[str]:
    """Return fail-closed violations for one queue-trend document."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [_error("unknown root_type", "queue report document must be an object")]

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
            _error(
                "missing_value field",
                "document missing fields: " + ", ".join(sorted(missing)),
            )
        )

    version = document.get("schema_version")
    if not _is_int(version) or version != SCHEMA_VERSION:
        errors.append(
            _error(
                "unknown schema_version",
                f"schema_version must be exactly {SCHEMA_VERSION}",
            )
        )

    window = document.get("window")
    if not isinstance(window, str) or not window.strip():
        errors.append(_error("missing_value window", "window must be a non-empty string"))

    for field in COUNT_FIELDS:
        if field in document:
            _check_nonneg_int(field, document.get(field), errors)

    if "age_seconds" in document:
        _check_nonneg_int("age_seconds", document.get("age_seconds"), errors)

    refs = document.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        errors.append(
            _error(
                "missing_value evidence_refs",
                "evidence_refs must be a non-empty list of non-empty strings",
            )
        )
        return errors
    for index, ref in enumerate(refs):
        if not isinstance(ref, str) or not ref.strip():
            errors.append(
                _error(
                    "unknown evidence_ref",
                    f"evidence_refs[{index}] must be a non-empty string",
                )
            )
    return errors


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
            _error(
                "unreadable json",
                f"invalid JSON in {path} at line {exc.lineno}, column {exc.colno}",
            )
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="queue-report JSON document")
    args = parser.parse_args(argv)
    errors = validate_queue_report(load_document(args.path))
    if errors:
        print("Queue-report schema validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"Queue-report schema v{SCHEMA_VERSION} accepted {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
