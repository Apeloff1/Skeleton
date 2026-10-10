#!/usr/bin/env python3
"""Independent exact-head verifier for VOL-003 canonical contract conformance.

The verifier intentionally does not import the canonical contract validator or
canonical serializer implementation. It re-derives producer/consumer coverage,
strict vector outcomes, serializer mirror parity, and masterplan bindings from
repository state and emits a deterministic exact-head receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path("machine/contract_conformance.json")
SCHEMAS = Path("machine/ai_runtime_schemas.json")
INTERFACES = Path("machine/capability_interfaces.json")
MASTERPLAN = Path("machine/ai_master_plan.json")
CANONICAL = Path("skeleton/contracts/canonical.py")
MIRROR = Path("skeleton/ai/runtime/contracts/canonical.py")

EXPECTED_CATALOG_SCHEMA = "skeleton.architecture.contract_conformance.v1"

QUALIFICATION_GAP = (
    "independent exact-head VOL-003 Contract Conformance Closure "
    "qualification remains pending"
)

REQUIRED_VOL003_PATHS = {
    "skeleton/contracts",
    "machine/ai_runtime_schemas.json",
    "machine/capability_interfaces.json",
    "skeleton/contracts/canonical.py",
    "skeleton/ai/runtime/contracts/canonical.py",
    "scripts/check_architecture_contract_conformance.py",
    "machine/contract_conformance.json",
    "scripts/verify_vol003_contract_conformance.py",
    ".github/workflows/vol003-contract-conformance.yml",
}
REQUIRED_VOL003_TESTS = {
    "skeleton/testing/test_contract_serialization_edges.py",
    "skeleton/testing/test_contract_compatibility.py",
    "skeleton/testing/test_contract_unicode_edges.py",
    "tests/test_architecture_contract_conformance.py",
    "tests/test_vol003_contract_conformance_independent.py",
}
REQUIRED_VOL003_EVALUATIONS = {
    "scripts/check_architecture_contract_conformance.py --json",
    "tests/test_architecture_contract_conformance.py",
    ".github/workflows/vol003-contract-conformance.yml",
    "scripts/verify_vol003_contract_conformance.py",
}
REQUIRED_REQUIREMENT_PHRASES = (
    "stable identity",
    "Fail closed",
    "absent/null",
)


class VerificationError(RuntimeError):
    """Independent VOL-003 authority could not be read safely."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot load JSON authority {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _strict_json(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite constant: {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    value = json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )
    _validate_portable_scalars(value)
    return value


def _validate_portable_scalars(value: Any, *, _depth: int = 0) -> None:
    # Independent vector replayers apply the same portable JSON limits
    # without importing or trusting the canonical serializer.
    if _depth > 64:
        raise ValueError("canonical JSON nesting depth exceeded")
    if isinstance(value, dict):
        for key, child in value.items():
            if any(0xD800 <= ord(char) <= 0xDFFF for char in key):
                raise ValueError("unpaired Unicode surrogate key")
            _validate_portable_scalars(child, _depth=_depth + 1)
        return
    if isinstance(value, list):
        for child in value:
            _validate_portable_scalars(child, _depth=_depth + 1)
        return
    if isinstance(value, str) and any(
        0xD800 <= ord(char) <= 0xDFFF for char in value
    ):
        raise ValueError("unpaired Unicode surrogate value")
    if type(value) is int and abs(value) > 9_007_199_254_740_991:
        raise ValueError("integer exceeds portable JSON range")
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite number")
        if value == 0.0 and math.copysign(1.0, value) < 0:
            raise ValueError("negative zero is not portable")


def _sample_value(
    field: dict[str, Any],
    scalars: dict[str, Any],
    enums: dict[str, Any],
) -> Any:
    field_type = field.get("type")
    if field.get("nullable") is True:
        return None
    enum_values = field.get("enum")
    if not isinstance(enum_values, list) and isinstance(field_type, str):
        enum_values = enums.get(field_type)
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]

    scalar = scalars.get(field_type, {}) if isinstance(field_type, str) else {}
    actual = scalar.get("type", field_type)
    if isinstance(actual, str) and actual.startswith("array<"):
        return []
    if actual == "string":
        if field_type == "Digest256":
            return "0" * 64
        if field_type == "RFC3339":
            return "2026-10-01T00:00:00Z"
        return "x"
    if actual == "integer":
        return max(1, int(scalar.get("minimum", 0)))
    if actual == "number":
        return max(0.0, float(scalar.get("minimum", 0)))
    if actual == "object" or field_type == "JsonObject":
        return {}
    if actual == "array":
        return []
    return "x"


def _base_record(record_name: str, schemas: dict[str, Any]) -> dict[str, Any]:
    records = schemas.get("records")
    if not isinstance(records, dict) or record_name not in records:
        raise ValueError(f"unknown record: {record_name}")
    record = records[record_name]
    fields = record.get("fields")
    if not isinstance(fields, dict):
        raise ValueError(f"record fields unavailable: {record_name}")
    scalars = schemas.get("scalar_types")
    enums = schemas.get("enums")
    return {
        name: _sample_value(
            spec,
            scalars if isinstance(scalars, dict) else {},
            enums if isinstance(enums, dict) else {},
        )
        for name, spec in fields.items()
        if isinstance(spec, dict)
    }


def _validate_record(
    record_name: str,
    payload: dict[str, Any],
    schemas: dict[str, Any],
) -> None:
    records = schemas.get("records")
    if not isinstance(records, dict):
        raise ValueError("schema records unavailable")
    record = records.get(record_name)
    if not isinstance(record, dict):
        raise ValueError(f"unknown record: {record_name}")
    fields = record.get("fields")
    if not isinstance(fields, dict):
        raise ValueError(f"record fields unavailable: {record_name}")
    if set(payload) != set(fields):
        raise ValueError("field set mismatch")

    enums = schemas.get("enums")
    enums = enums if isinstance(enums, dict) else {}
    for field_name, field_spec in fields.items():
        if not isinstance(field_spec, dict):
            raise ValueError("invalid field spec")
        value = payload[field_name]
        if value is None:
            if field_spec.get("nullable") is not True:
                raise ValueError(f"{field_name} is not nullable")
            continue
        field_type = field_spec.get("type")
        allowed = field_spec.get("enum")
        if not isinstance(allowed, list) and isinstance(field_type, str):
            candidate = enums.get(field_type)
            if isinstance(candidate, list):
                allowed = candidate
        if isinstance(allowed, list) and value not in allowed:
            raise ValueError(f"{field_name} has unknown enum value")


def _replay_vectors(
    catalog: dict[str, Any],
    schemas: dict[str, Any],
    errors: list[str],
) -> tuple[list[str], int]:
    vectors = catalog.get("vectors")
    if not isinstance(vectors, list) or not vectors:
        errors.append("conformance vectors must be a non-empty list")
        return [], 0

    ids: list[str] = []
    seen: set[str] = set()
    executed = 0
    for index, vector in enumerate(vectors):
        if not isinstance(vector, dict):
            errors.append(f"vector[{index}] must be an object")
            continue
        vector_id = vector.get("id")
        if not isinstance(vector_id, str) or not vector_id or vector_id in seen:
            errors.append(f"invalid/duplicate vector id: {vector_id!r}")
            continue
        seen.add(vector_id)
        ids.append(vector_id)

        expected = vector.get("expected")
        if expected not in {"accept", "reject"}:
            errors.append(f"{vector_id} has invalid expected result")
            continue

        accepted = False
        try:
            kind = vector.get("kind")
            if kind == "raw_json":
                payload = vector.get("payload")
                if not isinstance(payload, str):
                    raise ValueError("raw_json payload must be text")
                _strict_json(payload)
            elif kind == "schema_edge":
                record_name = vector.get("record")
                mutation = vector.get("mutation")
                if not isinstance(record_name, str) or not isinstance(mutation, str):
                    raise ValueError("schema edge vector missing record/mutation")
                payload = _base_record(record_name, schemas)
                op, value = mutation.split(":", 1)
                if op == "remove":
                    payload.pop(value, None)
                elif op == "null":
                    payload[value] = None
                elif op == "enum":
                    field, enum_value = value.split("=", 1)
                    payload[field] = enum_value
                else:
                    raise ValueError(f"unsupported mutation: {op}")
                _validate_record(record_name, payload, schemas)
            else:
                raise ValueError(f"unsupported vector kind: {kind}")
            accepted = True
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            accepted = False

        if accepted != (expected == "accept"):
            errors.append(
                f"{vector_id} replay mismatch: expected={expected} "
                f"actual={'accept' if accepted else 'reject'}"
            )
        executed += 1

    return sorted(ids), executed


def _verify_inventory(
    catalog: dict[str, Any],
    schemas: dict[str, Any],
    interfaces: dict[str, Any],
    errors: list[str],
) -> tuple[list[str], int]:
    records = schemas.get("records")
    if not isinstance(records, dict) or not records:
        errors.append("schema records must be non-empty")
        return [], 0

    entries = catalog.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("contract conformance entries must be non-empty")
        return [], 0

    by_name: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("contract conformance entry must be an object")
            continue
        name = entry.get("contract")
        if not isinstance(name, str) or not name or name in by_name:
            errors.append(f"invalid/duplicate contract inventory entry: {name!r}")
            continue
        by_name[name] = entry

    if set(by_name) != set(records):
        errors.append(
            "contract inventory/schema coverage drift: "
            f"missing={sorted(set(records) - set(by_name))} "
            f"extra={sorted(set(by_name) - set(records))}"
        )

    incoming: dict[str, set[str]] = {}
    interface_rows = interfaces.get("entries")
    if not isinstance(interface_rows, list):
        errors.append("capability interface entries must be a list")
        interface_rows = []
    for edge in interface_rows:
        if not isinstance(edge, dict):
            continue
        target = edge.get("target_plane")
        source = edge.get("source_plane")
        if isinstance(target, str) and isinstance(source, str):
            incoming.setdefault(target, set()).add(source)

    override_count = 0
    for name in sorted(set(by_name) & set(records)):
        entry = by_name[name]
        record = records[name]
        if not isinstance(record, dict):
            errors.append(f"schema record {name} must be an object")
            continue
        if entry.get("schema_version") != record.get("schema_version"):
            errors.append(f"{name} schema version drift")
        owner = record.get("owner_plane")
        if entry.get("producer_plane") != owner:
            errors.append(f"{name} producer/owner drift")

        consumers = entry.get("consumer_planes")
        if (
            not isinstance(consumers, list)
            or not consumers
            or len(consumers) != len(set(consumers))
            or not all(isinstance(item, str) and item for item in consumers)
        ):
            errors.append(f"{name} consumer set invalid")
            continue

        derived = sorted(incoming.get(owner, set()))
        mode = entry.get("consumer_derivation")
        if derived:
            if mode != "capability_interface_incoming_edges":
                errors.append(f"{name} consumer derivation mode drift")
            if sorted(consumers) != derived:
                errors.append(f"{name} derived consumer set drift")
            if entry.get("override_rationale") is not None:
                errors.append(f"{name} derived consumers carry override rationale")
        else:
            if mode != "reviewed_override":
                errors.append(f"{name} requires reviewed override")
            rationale = entry.get("override_rationale")
            if not isinstance(rationale, str) or not rationale.strip():
                errors.append(f"{name} reviewed override lacks rationale")
            override_count += 1

    return sorted(by_name), override_count


def _verify_mirror(root: Path, errors: list[str]) -> dict[str, str]:
    canonical = root / CANONICAL
    mirror = root / MIRROR
    if not canonical.is_file() or not mirror.is_file():
        errors.append("canonical serializer or AI mirror is missing")
        return {}
    try:
        canonical_bytes = canonical.read_bytes()
        mirror_bytes = mirror.read_bytes()
    except OSError as exc:
        errors.append(f"cannot read serializer mirror pair: {type(exc).__name__}")
        return {}
    if canonical_bytes != mirror_bytes:
        errors.append("canonical contract serializer mirror drift")
    source = canonical_bytes.decode("utf-8")
    for token in (
        "def canonical_json_bytes(",
        "allow_nan=False",
        "sort_keys=True",
        "def _validate_mapping_keys(",
        "def _validate_portable_json_scalars(",
        "MAX_PORTABLE_INTEGER",
        "integer exceeds portable JSON range",
        "negative zero is not portable canonical JSON",
        "canonical mappings require string keys",
        "authority_scope",
        "contract-conformance-only",
    ):
        if token not in source:
            errors.append(f"canonical serializer boundary token missing: {token}")
    return {
        "canonical": _digest_bytes(canonical_bytes),
        "mirror": _digest_bytes(mirror_bytes),
    }


def _verify_masterplan(master: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        errors.append("masterplan volumes must be a list")
        return {}
    volume = next(
        (
            row
            for row in volumes
            if isinstance(row, dict) and row.get("key") == "VOL-003"
        ),
        None,
    )
    if volume is None:
        errors.append("masterplan missing VOL-003")
        return {}

    if volume.get("title") != "Canonical Contract System":
        errors.append("VOL-003 title drift")
    if volume.get("scope") != "canonical-plan":
        errors.append("VOL-003 scope drift")
    if volume.get("implementation_status") not in {"implemented", "hardened", "verified"}:
        errors.append("VOL-003 implementation status below implemented")
    live_gaps = list(volume.get("gaps") or [])
    if live_gaps not in ([QUALIFICATION_GAP], []):
        errors.append(
            "VOL-003 gap state must be pending exact-head qualification or signed"
        )
    if not live_gaps and volume.get("completion_checkbox") is not True:
        errors.append("VOL-003 cannot clear qualification gap before signoff")
    if live_gaps and volume.get("completion_checkbox") is True:
        errors.append("VOL-003 cannot remain signed with pending qualification")

    paths = set(volume.get("implementation_paths") or [])
    tests = set(volume.get("tests") or [])
    evaluations = set(volume.get("evaluations") or [])
    for label, required, actual in (
        ("implementation path", REQUIRED_VOL003_PATHS, paths),
        ("test", REQUIRED_VOL003_TESTS, tests),
        ("evaluation", REQUIRED_VOL003_EVALUATIONS, evaluations),
    ):
        missing = sorted(required - actual)
        if missing:
            errors.append(f"VOL-003 {label} binding incomplete: {', '.join(missing)}")

    requirements = tuple(str(value) for value in volume.get("requirements") or [])
    for phrase in REQUIRED_REQUIREMENT_PHRASES:
        if not any(phrase in requirement for requirement in requirements):
            errors.append(f"VOL-003 requirement invariant lost: {phrase}")

    binding = {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "completion_checkbox_mark": volume.get("completion_checkbox_mark"),
        "enterprise_grade_state": volume.get("enterprise_grade_state"),
        "enterprise_grade_target": volume.get("enterprise_grade_target"),
        "gaps": list(volume.get("gaps") or []),
        "implementation_paths": sorted(paths),
        "tests": sorted(tests),
        "evaluations": sorted(evaluations),
    }
    binding["binding_digest"] = _digest_json(binding)
    return binding


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    catalog = _load(root / CATALOG)
    schemas = _load(root / SCHEMAS)
    interfaces = _load(root / INTERFACES)
    master = _load(root / MASTERPLAN)

    if catalog.get("schema_version") != EXPECTED_CATALOG_SCHEMA:
        errors.append("contract conformance catalog schema drift")
    if catalog.get("status") != "active":
        errors.append("contract conformance catalog must remain active")
    sources = catalog.get("sources")
    if sources != {
        "schema_catalog": SCHEMAS.as_posix(),
        "interface_registry": INTERFACES.as_posix(),
    }:
        errors.append("contract conformance source authority drift")

    binding = catalog.get("masterplan_binding")
    if not isinstance(binding, dict):
        errors.append("catalog masterplan_binding must be an object")
    else:
        if binding.get("volume_ref") != "VOL-003":
            errors.append("catalog bound to wrong masterplan volume")
        if binding.get("title") != "Canonical Contract System":
            errors.append("catalog/masterplan title drift")
        if binding.get("qualification_gap") != QUALIFICATION_GAP:
            errors.append("catalog qualification gap authority drift")
        retired_gaps = binding.get("retired_implementation_gaps")
        if not isinstance(retired_gaps, list) or not retired_gaps:
            errors.append("catalog retired implementation gaps must be non-empty")
        else:
            volume_rows = master.get("volumes")
            volume = next(
                (
                    row
                    for row in volume_rows
                    if isinstance(row, dict) and row.get("key") == "VOL-003"
                ),
                None,
            ) if isinstance(volume_rows, list) else None
            live_gaps = list(volume.get("gaps") or []) if isinstance(volume, dict) else []
            for retired_gap in retired_gaps:
                if retired_gap in live_gaps:
                    errors.append(
                        f"retired VOL-003 implementation gap reappeared: {retired_gap}"
                    )

    contracts, override_count = _verify_inventory(
        catalog,
        schemas,
        interfaces,
        errors,
    )
    vector_ids, executed = _replay_vectors(catalog, schemas, errors)
    mirror = _verify_mirror(root, errors)
    volume = _verify_masterplan(master, errors)

    source_digests = {
        "catalog": _digest_bytes((root / CATALOG).read_bytes()),
        "schema_catalog": _digest_bytes((root / SCHEMAS).read_bytes()),
        "interface_registry": _digest_bytes((root / INTERFACES).read_bytes()),
    }
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol003-contract-conformance-v1",
        "volume": "VOL-003",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "contract_count": len(contracts),
        "override_count": override_count,
        "vector_ids": vector_ids,
        "executed_vector_count": executed,
        "source_digests": source_digests,
        "serializer_mirror": mirror,
        "volume_binding": volume,
        "errors": errors,
        "valid": not errors,
    }
    receipt["receipt_digest"] = _digest_json(receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        receipt = {
            "schema_version": 1,
            "verifier": "independent-vol003-contract-conformance-v1",
            "volume": "VOL-003",
            "head_sha": (
                os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
                or os.environ.get("GITHUB_SHA", "").strip()
                or "unknown"
            ),
            "errors": [str(exc)],
            "valid": False,
        }
        receipt["receipt_digest"] = _digest_json(receipt)

    rendered = json.dumps(receipt, sort_keys=True, indent=2)
    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    elif receipt["valid"]:
        print(
            "VOL-003 independent contract conformance: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-003 independent contract conformance: FAIL")
        for error in receipt["errors"]:
            print(f" - {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
