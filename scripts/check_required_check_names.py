#!/usr/bin/env python3
"""Fail-closed check-name stability audit (#960 S007).

Classifies required merge-policy check names as ``stable``, ``renamed``,
``missing``, or ``unknown`` after workflow/job/check renames. Unknown always
fails closed so consumers cannot silently drop a required check.

This module classifies JSON only. It has no workflow mutation, rerun, cancel,
or GitHub write authority. Finding prefix: ``check-name-stability``.

Distinct from S001 PR blocker maps (check *state* rollup) and S002 run-state
classification (queued/cancelled/timed-out buckets).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_ID = "reserve-S007-check-name-stability"
CONFLICT_DOMAIN = "ci.readonly.check_name_stability"
CLASSES: tuple[str, ...] = (
    "stable",
    "renamed",
    "missing",
    "unknown",
)
CLASS_SET = frozenset(CLASSES)
_FINDING_PREFIX = "check-name-stability"

DOCUMENT_FIELDS = frozenset(
    {
        "schema_version",
        "task_id",
        "conflict_domain",
        "required_checks",
        "observed_checks",
        "renames",
    }
)
OBSERVED_FIELDS = frozenset({"name", "source", "workflow", "job"})
OBSERVED_REQUIRED_FIELDS = frozenset({"name"})
RENAME_FIELDS = frozenset({"from", "to", "kind"})
RENAME_REQUIRED_FIELDS = frozenset({"from", "to"})
KNOWN_SOURCES = frozenset({"workflow", "job", "check"})
KNOWN_RENAME_KINDS = frozenset({"workflow", "job", "check"})


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _norm_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def classify_required_check(
    name: object,
    *,
    observed_names: frozenset[str] | None,
    rename_map: Mapping[str, str | None] | None,
) -> str:
    """Return exactly one closed class. Unknown evidence fails closed."""

    required = _norm_name(name)
    if required is None:
        return "unknown"
    if observed_names is None or rename_map is None:
        return "unknown"

    mapped = rename_map.get(required, _UNSET)
    if required in observed_names:
        if mapped is not _UNSET:
            return "unknown"
        return "stable"
    if mapped is _UNSET:
        return "missing"
    if mapped is None:
        return "unknown"
    if mapped in observed_names:
        return "renamed"
    return "unknown"


_UNSET = object()


def _parse_observed(entries: object) -> tuple[frozenset[str] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(entries, list):
        return None, [_error("unknown observed_checks_type", "observed_checks must be a list")]
    names: set[str] = set()
    trusted = True
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            errors.append(
                _error(
                    "unknown observed_type",
                    f"observed_checks[{index}] must be an object",
                )
            )
            trusted = False
            continue
        unknown_fields = set(entry) - OBSERVED_FIELDS
        if unknown_fields:
            errors.append(
                _error(
                    "unknown field",
                    f"observed_checks[{index}] has unknown fields: "
                    + ", ".join(sorted(str(item) for item in unknown_fields)),
                )
            )
            trusted = False
        missing = OBSERVED_REQUIRED_FIELDS - set(entry)
        if missing:
            errors.append(
                _error(
                    "missing_value field",
                    f"observed_checks[{index}] missing fields: " + ", ".join(sorted(missing)),
                )
            )
            trusted = False
        check_name = _norm_name(entry.get("name"))
        if check_name is None:
            errors.append(
                _error(
                    "unknown observed_name",
                    f"observed_checks[{index}] name must be a non-empty string",
                )
            )
            trusted = False
        source = entry.get("source")
        if source is not None:
            if not isinstance(source, str) or source.strip() not in KNOWN_SOURCES:
                errors.append(
                    _error(
                        "unknown source",
                        f"observed_checks[{index}] source must be one of "
                        + ", ".join(sorted(KNOWN_SOURCES)),
                    )
                )
                trusted = False
        workflow = entry.get("workflow")
        if workflow is not None and (not isinstance(workflow, str) or not workflow.strip()):
            errors.append(
                _error(
                    "unknown workflow",
                    f"observed_checks[{index}] workflow must be a non-empty string",
                )
            )
            trusted = False
        job = entry.get("job")
        if job is not None and (not isinstance(job, str) or not job.strip()):
            errors.append(
                _error(
                    "unknown job",
                    f"observed_checks[{index}] job must be a non-empty string",
                )
            )
            trusted = False
        if check_name is not None and trusted:
            names.add(check_name)
    if not trusted:
        return None, errors
    return frozenset(names), errors


def _parse_renames(entries: object) -> tuple[dict[str, str | None] | None, list[str]]:
    errors: list[str] = []
    if entries is None:
        return {}, errors
    if not isinstance(entries, list):
        return None, [_error("unknown renames_type", "renames must be a list")]
    mapping: dict[str, str | None] = {}
    trusted = True
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            errors.append(_error("unknown rename_type", f"renames[{index}] must be an object"))
            trusted = False
            continue
        unknown_fields = set(entry) - RENAME_FIELDS
        if unknown_fields:
            errors.append(
                _error(
                    "unknown field",
                    f"renames[{index}] has unknown fields: "
                    + ", ".join(sorted(str(item) for item in unknown_fields)),
                )
            )
            trusted = False
        missing = RENAME_REQUIRED_FIELDS - set(entry)
        if missing:
            errors.append(
                _error(
                    "missing_value field",
                    f"renames[{index}] missing fields: " + ", ".join(sorted(missing)),
                )
            )
            trusted = False
        source = _norm_name(entry.get("from"))
        target = _norm_name(entry.get("to"))
        if source is None or target is None:
            errors.append(
                _error(
                    "unknown rename_name",
                    f"renames[{index}] from/to must be non-empty strings",
                )
            )
            trusted = False
            continue
        if source == target:
            errors.append(
                _error(
                    "unknown rename_identity",
                    f"renames[{index}] from and to must differ",
                )
            )
            trusted = False
            continue
        kind = entry.get("kind")
        if kind is not None:
            if not isinstance(kind, str) or kind.strip() not in KNOWN_RENAME_KINDS:
                errors.append(
                    _error(
                        "unknown rename_kind",
                        f"renames[{index}] kind must be one of "
                        + ", ".join(sorted(KNOWN_RENAME_KINDS)),
                    )
                )
                trusted = False
                continue
        if source in mapping and mapping[source] != target:
            mapping[source] = None
        elif source not in mapping:
            mapping[source] = target
    if not trusted:
        return None, errors
    return mapping, errors


def classify_document(document: object) -> tuple[list[dict[str, object]], list[str]]:
    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [], [_error("unknown root_type", "document must be an object")]

    unknown_fields = set(document) - DOCUMENT_FIELDS
    if unknown_fields:
        errors.append(
            _error(
                "unknown field",
                "document has unknown fields: " + ", ".join(sorted(str(item) for item in unknown_fields)),
            )
        )

    version = document.get("schema_version")
    if version != SCHEMA_VERSION:
        errors.append(_error("unknown schema_version", f"must be exactly {SCHEMA_VERSION}"))

    task_id = document.get("task_id")
    if task_id is not None and task_id != TASK_ID:
        errors.append(_error("unknown task_id", f"task_id must be exactly {TASK_ID!r}"))

    conflict_domain = document.get("conflict_domain")
    if conflict_domain is not None and conflict_domain != CONFLICT_DOMAIN:
        errors.append(
            _error(
                "unknown conflict_domain",
                f"conflict_domain must be exactly {CONFLICT_DOMAIN!r}",
            )
        )

    required_checks = document.get("required_checks")
    if not isinstance(required_checks, list):
        errors.append(_error("unknown required_checks_type", "required_checks must be a list"))
        return [], errors
    if not required_checks:
        errors.append(
            _error(
                "unknown required_checks_empty",
                "required_checks must be a non-empty list of check names",
            )
        )

    observed_names, observed_errors = _parse_observed(document.get("observed_checks"))
    errors.extend(observed_errors)
    rename_map, rename_errors = _parse_renames(document.get("renames"))
    errors.extend(rename_errors)

    evidence_trusted = observed_names is not None and rename_map is not None and not unknown_fields
    if version != SCHEMA_VERSION:
        evidence_trusted = False
    if task_id is not None and task_id != TASK_ID:
        evidence_trusted = False
    if conflict_domain is not None and conflict_domain != CONFLICT_DOMAIN:
        evidence_trusted = False

    rows: list[dict[str, object]] = []
    seen: dict[str, int] = {}
    for index, raw_name in enumerate(required_checks):
        required = _norm_name(raw_name)
        if required is not None and required in seen:
            errors.append(
                _error(
                    "unknown duplicate_required",
                    f"required_checks[{index}] duplicates required_checks[{seen[required]}]",
                )
            )
            klass = "unknown"
        else:
            if required is not None:
                seen[required] = index
            klass = classify_required_check(
                raw_name,
                observed_names=observed_names if evidence_trusted else None,
                rename_map=rename_map if evidence_trusted else None,
            )
        mapped = None
        if required is not None and rename_map is not None:
            mapped = rename_map.get(required)
        rows.append(
            {
                "index": index,
                "name": raw_name if isinstance(raw_name, str) else None,
                "class": klass,
                "observed_as": mapped if klass == "renamed" else (required if klass == "stable" else None),
            }
        )
        if klass == "unknown":
            errors.append(
                _error("unknown unclassified", f"required_checks[{index}] name={raw_name!r}")
            )
        elif klass == "renamed":
            errors.append(
                _error(
                    "renamed check",
                    f"required_checks[{index}] {required!r} now reports as {mapped!r}",
                )
            )
        elif klass == "missing":
            errors.append(
                _error(
                    "missing check",
                    f"required_checks[{index}] {required!r} is not emitted after workflow/job/check names",
                )
            )
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
    parser.add_argument(
        "path",
        type=Path,
        help="JSON document with schema_version, required_checks, observed_checks, optional renames",
    )
    args = parser.parse_args(argv)
    rows, errors = classify_document(load_document(args.path))
    counts = {name: 0 for name in CLASSES}
    for row in rows:
        counts[str(row["class"])] += 1
    print(
        "Check-name stability: " + ", ".join(f"{name}={counts[name]}" for name in CLASSES)
    )
    if errors:
        print("Check-name stability failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
