#!/usr/bin/env python3
"""Versioned fail-closed save-schema *migration* fixture contract (#960 S043).

This checker validates fixtures that describe how an old game save schema
moves to a newer known schema. It is not a game save system, not the S042
save-state payload schema, and not the S171 durable-state store inventory.

Closed save-schema versions: 1, 2, 3. Compatible migrations are identity
and forward-only (1→2, 2→3, 1→3). Incompatible versions (downgrades) fail
closed. Unknown versions, missing from/to, extra fields, and a successful
migration without evidence fail closed.

Finding prefix: ``save-migration``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_ID = "reserve-S043-save-schema-migration"
CONFLICT_DOMAIN = "game.spec.save_migration"
KIND = "save_schema_migration"
SAVE_SCHEMA_VERSIONS: tuple[int, ...] = (1, 2, 3)
SAVE_SCHEMA_VERSION_SET = frozenset(SAVE_SCHEMA_VERSIONS)
COMPATIBLE_MIGRATIONS = frozenset(
    {
        (1, 1),
        (2, 2),
        (3, 3),
        (1, 2),
        (2, 3),
        (1, 3),
    }
)
OUTCOMES: tuple[str, ...] = ("success",)
OUTCOME_SET = frozenset(OUTCOMES)
STEP_OPS: tuple[str, ...] = ("rename_field", "add_field", "drop_field", "identity")
STEP_OP_SET = frozenset(STEP_OPS)
DOCUMENT_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "fixture_id",
        "from_version",
        "to_version",
        "outcome",
        "source_digest",
        "expected_digest",
        "steps",
        "evidence_refs",
    }
)
STEP_FIELDS = frozenset({"op", "path"})
# S042 save-state payload keys and S171 durable-state inventory keys must never
# leak into this migration-fixture contract.
S042_SAVE_STATE_FIELDS = frozenset(
    {"player", "world", "mechanics", "inventory", "clock", "scene", "quest"}
)
S171_DURABLE_STATE_FIELDS = frozenset(
    {
        "store_id",
        "family",
        "lease",
        "checkpoint",
        "run_id",
        "persistence",
        "corruption_policy",
        "recovery_policy",
    }
)
_FINDING_PREFIX = "save-migration"


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_known_version(field: str, value: object, errors: list[str]) -> int | None:
    if value is None:
        errors.append(_error("missing_value " + field, f"{field} is required"))
        return None
    if not _is_int(value):
        errors.append(_error("unknown version", f"{field} must be a known integer save-schema version"))
        return None
    if value not in SAVE_SCHEMA_VERSION_SET:
        errors.append(
            _error(
                "unknown version",
                f"{field} {value!r} is not in the closed save-schema set {SAVE_SCHEMA_VERSIONS}",
            )
        )
        return None
    return value


def validate_save_schema_migration(document: object) -> list[str]:
    """Return fail-closed violations for one save-schema migration fixture."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [_error("unknown root_type", "save-schema migration document must be an object")]

    unknown = set(document) - DOCUMENT_FIELDS
    if unknown:
        extras = ", ".join(sorted(str(item) for item in unknown))
        errors.append(_error("unknown field", "document has unknown fields: " + extras))
        overlap_s042 = unknown & S042_SAVE_STATE_FIELDS
        if overlap_s042:
            errors.append(
                _error(
                    "unknown save_state_field",
                    "S042 save-state payload fields are out of scope: "
                    + ", ".join(sorted(overlap_s042)),
                )
            )
        overlap_s171 = unknown & S171_DURABLE_STATE_FIELDS
        if overlap_s171:
            errors.append(
                _error(
                    "unknown durable_state_field",
                    "S171 durable-state fields are out of scope: "
                    + ", ".join(sorted(overlap_s171)),
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
    if "from_version" in missing:
        errors.append(_error("missing_value from_version", "from_version is required"))
    if "to_version" in missing:
        errors.append(_error("missing_value to_version", "to_version is required"))

    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(_error("unknown schema_version", f"schema_version must be exactly {SCHEMA_VERSION}"))

    kind = document.get("kind")
    if kind != KIND:
        errors.append(_error("unknown kind", f"kind must be exactly {KIND!r}"))

    fixture_id = document.get("fixture_id")
    if not _nonempty_str(fixture_id):
        errors.append(_error("missing_value fixture_id", "fixture_id must be a non-empty string"))

    from_version = None
    to_version = None
    if "from_version" in document:
        from_version = _check_known_version("from_version", document.get("from_version"), errors)
    if "to_version" in document:
        to_version = _check_known_version("to_version", document.get("to_version"), errors)
    if from_version is not None and to_version is not None:
        pair = (from_version, to_version)
        if pair not in COMPATIBLE_MIGRATIONS:
            errors.append(
                _error(
                    "unknown incompatible_version",
                    f"migration {from_version}→{to_version} is incompatible and must fail closed",
                )
            )

    outcome = document.get("outcome")
    if outcome not in OUTCOME_SET:
        errors.append(_error("unknown outcome", f"outcome {outcome!r} is not in the closed set {OUTCOMES}"))

    source_digest = document.get("source_digest")
    if not _nonempty_str(source_digest):
        errors.append(_error("missing_value source_digest", "source_digest must be a non-empty string"))
    expected_digest = document.get("expected_digest")
    if not _nonempty_str(expected_digest):
        errors.append(
            _error(
                "missing_value expected_digest",
                "successful migration requires a non-empty expected_digest",
            )
        )

    steps = document.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append(_error("missing_value steps", "steps must be a non-empty list"))
    else:
        for index, step in enumerate(steps):
            prefix = f"steps[{index}]"
            if not isinstance(step, Mapping):
                errors.append(_error("unknown step_type", f"{prefix} must be an object"))
                continue
            extra_step = set(step) - STEP_FIELDS
            if extra_step:
                errors.append(
                    _error(
                        "unknown field",
                        f"{prefix} has unknown fields: "
                        + ", ".join(sorted(str(field) for field in extra_step)),
                    )
                )
            missing_step = STEP_FIELDS - set(step)
            if missing_step:
                errors.append(
                    _error(
                        "missing_value field",
                        f"{prefix} missing fields: " + ", ".join(sorted(missing_step)),
                    )
                )
            op = step.get("op")
            if op not in STEP_OP_SET:
                errors.append(_error("unknown step_op", f"{prefix} op {op!r} is not in the closed set"))
            path = step.get("path")
            if not _nonempty_str(path):
                errors.append(_error("missing_value path", f"{prefix} path must be a non-empty string"))

    refs = document.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        errors.append(
            _error(
                "missing_value evidence_refs",
                "successful migration requires a non-empty evidence_refs list",
            )
        )
        return errors
    for ref_index, ref in enumerate(refs):
        if not _nonempty_str(ref):
            errors.append(
                _error(
                    "unknown evidence_ref",
                    f"evidence_refs[{ref_index}] must be a non-empty string",
                )
            )
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
    parser.add_argument("path", type=Path, help="save-schema migration JSON fixture")
    args = parser.parse_args(argv)
    errors = validate_save_schema_migration(load_document(args.path))
    if errors:
        print("Save-schema migration validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"Save-schema migration fixture v{SCHEMA_VERSION} accepted {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
