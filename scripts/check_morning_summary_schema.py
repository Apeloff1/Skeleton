#!/usr/bin/env python3
"""Versioned fail-closed morning-summary schema (#969 S090).

Closed categories: accepted, rejected, blocked, deferred, flaky, unlocked.
Every item requires at least one evidence ref. Unknown categories, unknown
fields, and missing evidence fail closed. Unique prefix: ``morning-summary``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
CATEGORIES: tuple[str, ...] = (
    "accepted",
    "rejected",
    "blocked",
    "deferred",
    "flaky",
    "unlocked",
)
CATEGORY_SET = frozenset(CATEGORIES)
DOCUMENT_FIELDS = frozenset({"schema_version", "window", "items"})
ITEM_FIELDS = frozenset({"category", "title", "evidence_refs"})
_FINDING_PREFIX = "morning-summary"


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def validate_morning_summary(document: object) -> list[str]:
    """Return fail-closed violations for one morning-summary document."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [_error("unknown root_type", "morning summary document must be an object")]

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
    if version != SCHEMA_VERSION:
        errors.append(
            _error(
                "unknown schema_version",
                f"schema_version must be exactly {SCHEMA_VERSION}",
            )
        )

    window = document.get("window")
    if not isinstance(window, str) or not window.strip():
        errors.append(_error("missing_value window", "window must be a non-empty string"))

    items = document.get("items")
    if not isinstance(items, list):
        errors.append(_error("unknown items_type", "items must be a list"))
        return errors

    for index, item in enumerate(items):
        prefix = f"items[{index}]"
        if not isinstance(item, Mapping):
            errors.append(_error("unknown item_type", f"{prefix} must be an object"))
            continue
        unknown_item = set(item) - ITEM_FIELDS
        if unknown_item:
            errors.append(
                _error(
                    "unknown field",
                    f"{prefix} has unknown fields: "
                    + ", ".join(sorted(str(field) for field in unknown_item)),
                )
            )
        category = item.get("category")
        if category not in CATEGORY_SET:
            errors.append(
                _error(
                    "unknown category",
                    f"{prefix} category {category!r} is not in the closed set",
                )
            )
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(_error("missing_value title", f"{prefix} title must be a non-empty string"))
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(
                _error(
                    "missing_value evidence_refs",
                    f"{prefix} evidence_refs must be a non-empty list",
                )
            )
            continue
        for ref_index, ref in enumerate(refs):
            if not isinstance(ref, str) or not ref.strip():
                errors.append(
                    _error(
                        "unknown evidence_ref",
                        f"{prefix} evidence_refs[{ref_index}] must be a non-empty string",
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
    parser.add_argument("path", type=Path, help="morning-summary JSON document")
    args = parser.parse_args(argv)
    errors = validate_morning_summary(load_document(args.path))
    if errors:
        print("Morning-summary schema validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"Morning-summary schema v{SCHEMA_VERSION} accepted {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
