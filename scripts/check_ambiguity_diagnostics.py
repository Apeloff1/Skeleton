#!/usr/bin/env python3
"""Versioned fail-closed creator ambiguity diagnostics spec (#969 S035).

Closed vocabulary of typed ambiguity and missing-constraint categories with a
deterministic fail/clarify mapping. Unknown categories, unknown fields, kind
or disposition drift, and missing evidence fail closed. An unknown category
is never guessed as ``clarify``.

Finding prefix: ``ambiguity-diagnostics``. Distinct from morning-summary
categories and from queue-trend counts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, NamedTuple, Sequence


SCHEMA_VERSION = 1
TASK_KEY = "reserve-S035-ambiguity-diagnostics-spec"
CONFLICT_DOMAIN = "creator.spec.ambiguity"

KIND_AMBIGUITY = "ambiguity"
KIND_MISSING_CONSTRAINT = "missing_constraint"
KINDS: tuple[str, ...] = (KIND_AMBIGUITY, KIND_MISSING_CONSTRAINT)
KIND_SET = frozenset(KINDS)

DISPOSITION_FAIL = "fail"
DISPOSITION_CLARIFY = "clarify"
DISPOSITIONS: tuple[str, ...] = (DISPOSITION_FAIL, DISPOSITION_CLARIFY)
DISPOSITION_SET = frozenset(DISPOSITIONS)

DOCUMENT_FIELDS = frozenset({"schema_version", "request_id", "diagnostics"})
DIAGNOSTIC_FIELDS = frozenset(
    {"category", "kind", "disposition", "subject", "evidence_refs"}
)
_FINDING_PREFIX = "ambiguity-diagnostics"


class CategoryRule(NamedTuple):
    category: str
    kind: str
    disposition: str


# Closed catalog. Fail when two interpretations cannot coexist or a safety
# boundary is absent. Clarify when a creator can answer without guessing.
CATEGORY_RULES: tuple[CategoryRule, ...] = (
    CategoryRule("conflicting_constraints", KIND_AMBIGUITY, DISPOSITION_FAIL),
    CategoryRule("duplicate_identity", KIND_AMBIGUITY, DISPOSITION_FAIL),
    CategoryRule("ambiguous_reference", KIND_AMBIGUITY, DISPOSITION_FAIL),
    CategoryRule("competing_goals", KIND_AMBIGUITY, DISPOSITION_CLARIFY),
    CategoryRule("underspecified_scope", KIND_AMBIGUITY, DISPOSITION_CLARIFY),
    CategoryRule("ambiguous_platform", KIND_AMBIGUITY, DISPOSITION_CLARIFY),
    CategoryRule("conflicting_style", KIND_AMBIGUITY, DISPOSITION_CLARIFY),
    CategoryRule("missing_safety_boundary", KIND_MISSING_CONSTRAINT, DISPOSITION_FAIL),
    CategoryRule("missing_constraint_value", KIND_MISSING_CONSTRAINT, DISPOSITION_FAIL),
    CategoryRule("missing_player_count", KIND_MISSING_CONSTRAINT, DISPOSITION_CLARIFY),
    CategoryRule("missing_win_condition", KIND_MISSING_CONSTRAINT, DISPOSITION_CLARIFY),
    CategoryRule("missing_platform", KIND_MISSING_CONSTRAINT, DISPOSITION_CLARIFY),
    CategoryRule("missing_success_criteria", KIND_MISSING_CONSTRAINT, DISPOSITION_CLARIFY),
    CategoryRule("missing_input_surface", KIND_MISSING_CONSTRAINT, DISPOSITION_CLARIFY),
    CategoryRule("missing_output_artifact", KIND_MISSING_CONSTRAINT, DISPOSITION_CLARIFY),
)
CATEGORY_INDEX: dict[str, CategoryRule] = {rule.category: rule for rule in CATEGORY_RULES}
CATEGORIES: tuple[str, ...] = tuple(rule.category for rule in CATEGORY_RULES)
CATEGORY_SET = frozenset(CATEGORIES)


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def resolve_behavior(category: object) -> tuple[str | None, str | None]:
    """Return ``(disposition, error)`` for one category.

    Unknown categories fail closed. The disposition is never guessed.
    """

    if not isinstance(category, str) or category not in CATEGORY_INDEX:
        return None, _error(
            "unknown category",
            f"category {category!r} is not in the closed set",
        )
    return CATEGORY_INDEX[category].disposition, None


def catalog_integrity_errors() -> list[str]:
    """Fail closed if the frozen catalog itself is inconsistent."""

    errors: list[str] = []
    if len(CATEGORIES) != len(CATEGORY_SET):
        errors.append(_error("unknown catalog", "category ids must be unique"))
    if "unknown" in CATEGORY_SET:
        errors.append(_error("unknown catalog", "unknown is not a typed category"))
    for rule in CATEGORY_RULES:
        if rule.kind not in KIND_SET:
            errors.append(
                _error(
                    "unknown kind",
                    f"catalog category {rule.category!r} has unknown kind {rule.kind!r}",
                )
            )
        if rule.disposition not in DISPOSITION_SET:
            errors.append(
                _error(
                    "unknown disposition",
                    f"catalog category {rule.category!r} has unknown disposition {rule.disposition!r}",
                )
            )
    return errors


def aggregate_disposition(categories: Sequence[object]) -> tuple[str | None, list[str]]:
    """Deterministic document disposition: any fail wins; else clarify.

    An empty category list has no action (``None``). Unknown categories fail
    closed before any disposition is returned.
    """

    errors: list[str] = []
    saw_fail = False
    saw_clarify = False
    for category in categories:
        disposition, error = resolve_behavior(category)
        if error is not None:
            errors.append(error)
            continue
        if disposition == DISPOSITION_FAIL:
            saw_fail = True
        elif disposition == DISPOSITION_CLARIFY:
            saw_clarify = True
    if errors:
        return None, errors
    if saw_fail:
        return DISPOSITION_FAIL, []
    if saw_clarify:
        return DISPOSITION_CLARIFY, []
    return None, []


def _check_diagnostic(index: int, item: object, errors: list[str]) -> str | None:
    prefix = f"diagnostics[{index}]"
    if not isinstance(item, Mapping):
        errors.append(_error("unknown item_type", f"{prefix} must be an object"))
        return None
    unknown_item = set(item) - DIAGNOSTIC_FIELDS
    if unknown_item:
        errors.append(
            _error(
                "unknown field",
                f"{prefix} has unknown fields: "
                + ", ".join(sorted(str(field) for field in unknown_item)),
            )
        )
    missing_item = DIAGNOSTIC_FIELDS - set(item)
    if missing_item:
        errors.append(
            _error(
                "missing_value field",
                f"{prefix} missing fields: " + ", ".join(sorted(missing_item)),
            )
        )

    category = item.get("category")
    disposition, category_error = resolve_behavior(category)
    if category_error is not None:
        errors.append(
            _error(
                "unknown category",
                f"{prefix} category {category!r} is not in the closed set",
            )
        )
        rule = None
    else:
        rule = CATEGORY_INDEX[str(category)]

    kind = item.get("kind")
    if kind not in KIND_SET:
        errors.append(
            _error(
                "unknown kind",
                f"{prefix} kind {kind!r} is not in the closed set",
            )
        )
    elif rule is not None and kind != rule.kind:
        errors.append(
            _error(
                "unknown kind",
                f"{prefix} kind {kind!r} does not match catalog kind {rule.kind!r}",
            )
        )

    claimed = item.get("disposition")
    if claimed not in DISPOSITION_SET:
        errors.append(
            _error(
                "unknown disposition",
                f"{prefix} disposition {claimed!r} is not in the closed set",
            )
        )
    elif rule is not None and claimed != disposition:
        errors.append(
            _error(
                "unknown disposition",
                f"{prefix} disposition {claimed!r} does not match catalog "
                f"{disposition!r} for category {category!r}",
            )
        )

    subject = item.get("subject")
    if not isinstance(subject, str) or not subject.strip():
        errors.append(
            _error("missing_value subject", f"{prefix} subject must be a non-empty string")
        )

    refs = item.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        errors.append(
            _error(
                "missing_value evidence_refs",
                f"{prefix} evidence_refs must be a non-empty list",
            )
        )
        return disposition
    for ref_index, ref in enumerate(refs):
        if not isinstance(ref, str) or not ref.strip():
            errors.append(
                _error(
                    "unknown evidence_ref",
                    f"{prefix} evidence_refs[{ref_index}] must be a non-empty string",
                )
            )
    return disposition


def validate_ambiguity_diagnostics(document: object) -> list[str]:
    """Return fail-closed violations for one ambiguity-diagnostics document."""

    errors = catalog_integrity_errors()
    if not isinstance(document, Mapping):
        return [*errors, _error("unknown root_type", "ambiguity diagnostics document must be an object")]

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
    if not isinstance(version, int) or isinstance(version, bool) or version != SCHEMA_VERSION:
        errors.append(
            _error(
                "unknown schema_version",
                f"schema_version must be exactly {SCHEMA_VERSION}",
            )
        )

    request_id = document.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        errors.append(
            _error("missing_value request_id", "request_id must be a non-empty string")
        )

    diagnostics = document.get("diagnostics")
    if not isinstance(diagnostics, list):
        errors.append(_error("unknown diagnostics_type", "diagnostics must be a list"))
        return errors

    for index, item in enumerate(diagnostics):
        _check_diagnostic(index, item, errors)
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
    parser.add_argument("path", type=Path, help="ambiguity-diagnostics JSON document")
    args = parser.parse_args(argv)
    errors = validate_ambiguity_diagnostics(load_document(args.path))
    if errors:
        print("Ambiguity-diagnostics schema validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"Ambiguity-diagnostics schema v{SCHEMA_VERSION} accepted {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
