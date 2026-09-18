#!/usr/bin/env python3
"""Versioned fail-closed asset budget evidence schema (#969 S070).

Closed axes: memory, disk, dimension, duration, complexity. Values are
backend-neutral (bytes, extents, milliseconds, primitive counts). Unknown
fields, unknown units, unknown kinds, wrong types, negative counts, and
missing per-axis evidence fail closed.

Distinct from asset catalog identity/digest/lineage work. Unique prefix:
``asset-budget``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_KEY = "reserve-S070-asset-budget-schema"
CONFLICT_DOMAIN = "assets.spec.budget_evidence"
AXES: tuple[str, ...] = ("memory", "disk", "dimension", "duration", "complexity")
KINDS: tuple[str, ...] = (
    "raster",
    "audio",
    "video",
    "geometry",
    "animation",
    "volume",
    "document",
)
KIND_SET = frozenset(KINDS)
DIMENSION_UNITS: tuple[str, ...] = ("texel", "sample", "voxel", "pixel")
DIMENSION_UNIT_SET = frozenset(DIMENSION_UNITS)
COMPLEXITY_UNITS: tuple[str, ...] = ("primitive", "sample", "element")
COMPLEXITY_UNIT_SET = frozenset(COMPLEXITY_UNITS)
DOCUMENT_FIELDS = frozenset({"schema_version", "asset_id", "kind", *AXES})
MEMORY_FIELDS = frozenset({"bytes", "evidence_refs"})
DISK_FIELDS = frozenset({"bytes", "evidence_refs"})
DIMENSION_FIELDS = frozenset({"width", "height", "depth", "unit", "evidence_refs"})
DURATION_FIELDS = frozenset({"milliseconds", "evidence_refs"})
COMPLEXITY_FIELDS = frozenset({"value", "unit", "evidence_refs"})
AXIS_FIELDS = {
    "memory": MEMORY_FIELDS,
    "disk": DISK_FIELDS,
    "dimension": DIMENSION_FIELDS,
    "duration": DURATION_FIELDS,
    "complexity": COMPLEXITY_FIELDS,
}
_FINDING_PREFIX = "asset-budget"


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_nonneg_int(path: str, value: object, errors: list[str]) -> None:
    if not _is_int(value):
        errors.append(_error("unknown type", f"{path} must be an integer >= 0"))
        return
    if value < 0:
        errors.append(_error("unknown negative", f"{path} must be >= 0"))


def _check_evidence_refs(path: str, refs: object, errors: list[str]) -> None:
    if not isinstance(refs, list) or not refs:
        errors.append(
            _error(
                "missing_value evidence_refs",
                f"{path} evidence_refs must be a non-empty list of non-empty strings",
            )
        )
        return
    for index, ref in enumerate(refs):
        if not isinstance(ref, str) or not ref.strip():
            errors.append(
                _error(
                    "unknown evidence_ref",
                    f"{path} evidence_refs[{index}] must be a non-empty string",
                )
            )


def _check_closed_object(
    path: str,
    value: object,
    allowed: frozenset[str],
    errors: list[str],
) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        errors.append(_error("unknown axis_type", f"{path} must be an object"))
        return None
    unknown = set(value) - allowed
    if unknown:
        errors.append(
            _error(
                "unknown field",
                f"{path} has unknown fields: " + ", ".join(sorted(str(item) for item in unknown)),
            )
        )
    missing = allowed - set(value)
    if missing:
        errors.append(
            _error(
                "missing_value field",
                f"{path} missing fields: " + ", ".join(sorted(missing)),
            )
        )
    return value


def _check_memory(axis: Mapping[str, object], errors: list[str]) -> None:
    if "bytes" in axis:
        _check_nonneg_int("memory.bytes", axis.get("bytes"), errors)
    if "evidence_refs" in axis:
        _check_evidence_refs("memory", axis.get("evidence_refs"), errors)


def _check_disk(axis: Mapping[str, object], errors: list[str]) -> None:
    if "bytes" in axis:
        _check_nonneg_int("disk.bytes", axis.get("bytes"), errors)
    if "evidence_refs" in axis:
        _check_evidence_refs("disk", axis.get("evidence_refs"), errors)


def _check_dimension(axis: Mapping[str, object], errors: list[str]) -> None:
    for name in ("width", "height", "depth"):
        if name in axis:
            _check_nonneg_int(f"dimension.{name}", axis.get(name), errors)
    if "unit" in axis:
        unit = axis.get("unit")
        if unit not in DIMENSION_UNIT_SET:
            errors.append(
                _error(
                    "unknown dimension_unit",
                    f"dimension.unit {unit!r} is not in the closed set",
                )
            )
    if "evidence_refs" in axis:
        _check_evidence_refs("dimension", axis.get("evidence_refs"), errors)


def _check_duration(axis: Mapping[str, object], errors: list[str]) -> None:
    if "milliseconds" in axis:
        _check_nonneg_int("duration.milliseconds", axis.get("milliseconds"), errors)
    if "evidence_refs" in axis:
        _check_evidence_refs("duration", axis.get("evidence_refs"), errors)


def _check_complexity(axis: Mapping[str, object], errors: list[str]) -> None:
    if "value" in axis:
        _check_nonneg_int("complexity.value", axis.get("value"), errors)
    if "unit" in axis:
        unit = axis.get("unit")
        if unit not in COMPLEXITY_UNIT_SET:
            errors.append(
                _error(
                    "unknown complexity_unit",
                    f"complexity.unit {unit!r} is not in the closed set",
                )
            )
    if "evidence_refs" in axis:
        _check_evidence_refs("complexity", axis.get("evidence_refs"), errors)


_AXIS_CHECKERS = {
    "memory": _check_memory,
    "disk": _check_disk,
    "dimension": _check_dimension,
    "duration": _check_duration,
    "complexity": _check_complexity,
}


def validate_asset_budget(document: object) -> list[str]:
    """Return fail-closed violations for one asset-budget evidence document."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [_error("unknown root_type", "asset budget document must be an object")]

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

    asset_id = document.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id.strip():
        errors.append(_error("missing_value asset_id", "asset_id must be a non-empty string"))

    kind = document.get("kind")
    if kind not in KIND_SET:
        errors.append(
            _error("unknown kind", f"kind {kind!r} is not in the closed set")
        )

    for axis_name in AXES:
        if axis_name not in document:
            continue
        axis = _check_closed_object(
            axis_name,
            document.get(axis_name),
            AXIS_FIELDS[axis_name],
            errors,
        )
        if axis is None:
            continue
        _AXIS_CHECKERS[axis_name](axis, errors)
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
    parser.add_argument("path", type=Path, help="asset-budget JSON document")
    args = parser.parse_args(argv)
    errors = validate_asset_budget(load_document(args.path))
    if errors:
        print("Asset-budget schema validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"Asset-budget schema v{SCHEMA_VERSION} accepted {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
