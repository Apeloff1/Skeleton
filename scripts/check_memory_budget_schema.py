#!/usr/bin/env python3
"""Versioned fail-closed bounded-retrieval memory-budget schema (#969 S057).

Explicit item/token/byte budgets, provenance requiredness, and closed
truncation/fallback enums. Unknown budget kinds, unknown budget object
fields, unknown enums, missing evidence, and non-positive limits fail
closed.

This is ``rag.spec.bounded_retrieval`` (task ``reserve-S057-memory-budget-review``).
It does not inventory retrieval surfaces or classify adapters. Finding prefix:
``memory-budget``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_ID = "reserve-S057-memory-budget-review"
CONFLICT_DOMAIN = "rag.spec.bounded_retrieval"
_FINDING_PREFIX = "memory-budget"

BUDGET_KINDS: tuple[str, ...] = ("item", "token", "byte")
BUDGET_KIND_SET = frozenset(BUDGET_KINDS)
BUDGET_UNITS: dict[str, str] = {
    "item": "items",
    "token": "tokens",
    "byte": "bytes",
}
BUDGET_OBJECT_FIELDS = frozenset({"limit", "unit"})

TRUNCATION_POLICIES: tuple[str, ...] = (
    "reject_overflow",
    "drop_lowest_relevance",
    "truncate_content",
)
TRUNCATION_SET = frozenset(TRUNCATION_POLICIES)

FALLBACK_POLICIES: tuple[str, ...] = (
    "fail_closed",
    "empty_context",
)
FALLBACK_SET = frozenset(FALLBACK_POLICIES)

PROVENANCE_PRESENCE_FIELDS: tuple[str, ...] = (
    "source_repository",
    "source_revision",
    "source_path",
)
PROVENANCE_FIELDS = frozenset((*PROVENANCE_PRESENCE_FIELDS, "content_in_audit"))
PRESENCE_VALUES = frozenset({"required", "optional", "forbidden"})

DOCUMENT_FIELDS = frozenset(
    {
        "schema_version",
        "budgets",
        "provenance",
        "truncation",
        "fallback",
        "evidence_refs",
    }
)


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_budget(kind: str, value: object, errors: list[str]) -> None:
    prefix = f"budgets.{kind}"
    if not isinstance(value, Mapping):
        errors.append(_error("unknown budget_type", f"{prefix} must be an object"))
        return
    unknown = set(value) - BUDGET_OBJECT_FIELDS
    if unknown:
        errors.append(
            _error(
                "unknown budget_field",
                f"{prefix} has unknown fields: "
                + ", ".join(sorted(str(field) for field in unknown)),
            )
        )
    missing = BUDGET_OBJECT_FIELDS - set(value)
    if missing:
        errors.append(
            _error(
                "missing_value budget_field",
                f"{prefix} missing fields: " + ", ".join(sorted(missing)),
            )
        )
    limit = value.get("limit")
    if not _is_int(limit) or limit < 1:
        errors.append(_error("unknown limit", f"{prefix}.limit must be an integer >= 1"))
    unit = value.get("unit")
    expected = BUDGET_UNITS[kind]
    if unit != expected:
        errors.append(
            _error(
                "unknown unit",
                f"{prefix}.unit must be exactly {expected!r}",
            )
        )


def _check_provenance(value: object, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        errors.append(_error("unknown provenance_type", "provenance must be an object"))
        return
    unknown = set(value) - PROVENANCE_FIELDS
    if unknown:
        errors.append(
            _error(
                "unknown field",
                "provenance has unknown fields: "
                + ", ".join(sorted(str(field) for field in unknown)),
            )
        )
    missing = PROVENANCE_FIELDS - set(value)
    if missing:
        errors.append(
            _error(
                "missing_value field",
                "provenance missing fields: " + ", ".join(sorted(missing)),
            )
        )
    repository = value.get("source_repository")
    if repository != "required":
        errors.append(
            _error(
                "unknown provenance",
                "provenance.source_repository must be exactly 'required'",
            )
        )
    for field in ("source_revision", "source_path"):
        if field not in value:
            continue
        presence = value.get(field)
        if presence not in PRESENCE_VALUES:
            errors.append(
                _error(
                    "unknown provenance",
                    f"provenance.{field} must be one of "
                    + ", ".join(sorted(PRESENCE_VALUES)),
                )
            )
    if "content_in_audit" in value and value.get("content_in_audit") is not False:
        errors.append(
            _error(
                "unknown provenance",
                "provenance.content_in_audit must be exactly false",
            )
        )


def validate_memory_budget(document: object) -> list[str]:
    """Return fail-closed violations for one bounded-retrieval budget document."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [_error("unknown root_type", "memory budget document must be an object")]

    unknown = set(document) - DOCUMENT_FIELDS
    if unknown:
        errors.append(
            _error(
                "unknown field",
                "document has unknown fields: "
                + ", ".join(sorted(str(item) for item in unknown)),
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

    budgets = document.get("budgets")
    if not isinstance(budgets, Mapping):
        errors.append(_error("unknown budgets_type", "budgets must be an object"))
    else:
        unknown_kinds = set(budgets) - BUDGET_KIND_SET
        if unknown_kinds:
            errors.append(
                _error(
                    "unknown budget_field",
                    "budgets has unknown fields: "
                    + ", ".join(sorted(str(item) for item in unknown_kinds)),
                )
            )
        missing_kinds = BUDGET_KIND_SET - set(budgets)
        if missing_kinds:
            errors.append(
                _error(
                    "missing_value budget_field",
                    "budgets missing fields: " + ", ".join(sorted(missing_kinds)),
                )
            )
        for kind in BUDGET_KINDS:
            if kind not in budgets:
                continue
            _check_budget(kind, budgets.get(kind), errors)

    if "provenance" in document:
        _check_provenance(document.get("provenance"), errors)

    truncation = document.get("truncation")
    if truncation not in TRUNCATION_SET:
        errors.append(
            _error(
                "unknown truncation",
                f"truncation {truncation!r} is not in the closed set",
            )
        )
    fallback = document.get("fallback")
    if fallback not in FALLBACK_SET:
        errors.append(
            _error(
                "unknown fallback",
                f"fallback {fallback!r} is not in the closed set",
            )
        )

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
    parser.add_argument("path", type=Path, help="memory-budget JSON document")
    args = parser.parse_args(argv)
    errors = validate_memory_budget(load_document(args.path))
    if errors:
        print("Memory-budget schema validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"Memory-budget schema v{SCHEMA_VERSION} accepted {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
