#!/usr/bin/env python3
"""Validate canonical contract producer/consumer inventory and conformance vectors."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path("machine/contract_conformance.json")
MASTER = Path("machine/ai_master_plan.json")


class ContractConformanceError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractConformanceError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise ContractConformanceError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractConformanceError(f"{relative} must contain an object")
    return data


def _strict_json(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite constant: {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"duplicate key: {key}")
            out[key] = value
        return out

    return json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )


def _sample_value(field: dict[str, Any], scalars: dict[str, Any], enums: dict[str, Any]) -> Any:
    field_type = field.get("type")
    nullable = field.get("nullable") is True
    if nullable:
        return None
    if isinstance(field.get("enum"), list) and field["enum"]:
        return field["enum"][0]
    if field_type in enums and enums[field_type]:
        return enums[field_type][0]
    spec = scalars.get(field_type, {}) if isinstance(field_type, str) else {}
    actual = spec.get("type", field_type)
    if isinstance(actual, str) and actual.startswith("array<"):
        return []
    if actual == "string":
        if field_type == "Digest256":
            return "0" * 64
        if field_type == "RFC3339":
            return "2026-10-01T00:00:00Z"
        return "x"
    if actual == "integer":
        return max(1, int(spec.get("minimum", 0)))
    if actual == "number":
        return max(0, float(spec.get("minimum", 0)))
    if actual == "object":
        return {}
    if actual == "array":
        return []
    if field_type == "JsonObject":
        return {}
    return "x"


def _validate_record(record_name: str, payload: dict[str, Any], schemas: dict[str, Any]) -> None:
    record = schemas.get("records", {}).get(record_name)
    if not isinstance(record, dict):
        raise ValueError(f"unknown record {record_name}")
    scalars = schemas.get("scalar_types", {})
    enums = schemas.get("enums", {})
    fields = record.get("fields", {})
    if set(payload) != set(fields):
        missing = sorted(set(fields) - set(payload))
        extra = sorted(set(payload) - set(fields))
        raise ValueError(f"field set mismatch missing={missing} extra={extra}")
    for name, spec in fields.items():
        value = payload[name]
        if value is None:
            if spec.get("nullable") is not True:
                raise ValueError(f"{name} is not nullable")
            continue
        field_type = spec.get("type")
        allowed = spec.get("enum")
        if allowed is None and field_type in enums:
            allowed = enums[field_type]
        if isinstance(allowed, list) and value not in allowed:
            raise ValueError(f"{name} has unknown enum value")


def _base_record(record_name: str, schemas: dict[str, Any]) -> dict[str, Any]:
    record = schemas["records"][record_name]
    return {
        name: _sample_value(spec, schemas.get("scalar_types", {}), schemas.get("enums", {}))
        for name, spec in record["fields"].items()
    }


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    catalog = _load(root, CATALOG)
    master = _load(root, MASTER)
    sources = catalog.get("sources")
    if not isinstance(sources, dict):
        raise ContractConformanceError("sources must be an object")
    schemas = _load(root, Path(sources.get("schema_catalog", "")))
    interfaces = _load(root, Path(sources.get("interface_registry", "")))

    binding = catalog.get("masterplan_binding")
    if not isinstance(binding, dict):
        raise ContractConformanceError("masterplan_binding must be an object")
    volume = next(
        (v for v in master.get("volumes", []) if isinstance(v, dict) and v.get("key") == "VOL-003"),
        None,
    )
    if not isinstance(volume, dict):
        raise ContractConformanceError("masterplan must contain VOL-003")
    if binding.get("volume_ref") != "VOL-003" or binding.get("title") != volume.get("title"):
        raise ContractConformanceError("contract conformance must remain bound to VOL-003")
    qualification_gap = binding.get("qualification_gap")
    if not isinstance(qualification_gap, str) or not qualification_gap.strip():
        raise ContractConformanceError("VOL-003 qualification_gap must be non-empty")
    retired_gaps = binding.get("retired_implementation_gaps")
    if not isinstance(retired_gaps, list) or not all(
        isinstance(item, str) and item for item in retired_gaps
    ):
        raise ContractConformanceError(
            "VOL-003 retired_implementation_gaps must be non-empty strings"
        )
    live_gaps = list(volume.get("gaps") or [])
    if live_gaps not in ([qualification_gap], []):
        raise ContractConformanceError(
            "VOL-003 gap state must be pending exact-head qualification or signed"
        )
    for retired_gap in retired_gaps:
        if retired_gap in live_gaps:
            raise ContractConformanceError(
                f"retired VOL-003 implementation gap reappeared: {retired_gap!r}"
            )
    if not live_gaps and volume.get("completion_checkbox") is not True:
        raise ContractConformanceError(
            "VOL-003 cannot clear qualification gap before completion signoff"
        )
    if live_gaps and volume.get("completion_checkbox") is True:
        raise ContractConformanceError(
            "VOL-003 cannot remain signed with a pending qualification gap"
        )

    records = schemas.get("records")
    if not isinstance(records, dict) or not records:
        raise ContractConformanceError("schema catalog records must be non-empty")
    entries = catalog.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ContractConformanceError("contract inventory entries must be non-empty")

    by_name: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ContractConformanceError("contract inventory entry must be an object")
        name = entry.get("contract")
        if not isinstance(name, str) or not name:
            raise ContractConformanceError("contract inventory entry requires contract")
        if name in by_name:
            raise ContractConformanceError(f"duplicate contract inventory entry: {name}")
        by_name[name] = entry

    if set(by_name) != set(records):
        missing = sorted(set(records) - set(by_name))
        extra = sorted(set(by_name) - set(records))
        raise ContractConformanceError(
            f"contract inventory must cover schema records exactly; missing={missing}, extra={extra}"
        )

    incoming: dict[str, set[str]] = {}
    for edge in interfaces.get("entries", []):
        if not isinstance(edge, dict):
            continue
        target = edge.get("target_plane")
        source = edge.get("source_plane")
        if isinstance(target, str) and isinstance(source, str):
            incoming.setdefault(target, set()).add(source)

    override_count = 0
    for name, record in records.items():
        entry = by_name[name]
        if entry.get("schema_version") != record.get("schema_version"):
            raise ContractConformanceError(f"{name} schema_version drift")
        owner = record.get("owner_plane")
        if entry.get("producer_plane") != owner:
            raise ContractConformanceError(f"{name} producer must equal owner_plane")
        consumers = entry.get("consumer_planes")
        if not isinstance(consumers, list) or not consumers or len(consumers) != len(set(consumers)):
            raise ContractConformanceError(f"{name} consumer_planes must be unique/non-empty")
        derived = sorted(incoming.get(owner, set()))
        mode = entry.get("consumer_derivation")
        if derived:
            if mode != "capability_interface_incoming_edges" or sorted(consumers) != derived:
                raise ContractConformanceError(f"{name} consumer derivation drift")
            if entry.get("override_rationale") is not None:
                raise ContractConformanceError(f"{name} derived consumers cannot carry override rationale")
        else:
            if mode != "reviewed_override":
                raise ContractConformanceError(f"{name} requires reviewed consumer override")
            rationale = entry.get("override_rationale")
            if not isinstance(rationale, str) or not rationale.strip():
                raise ContractConformanceError(f"{name} override requires rationale")
            override_count += 1

    vectors = catalog.get("vectors")
    if not isinstance(vectors, list) or not vectors:
        raise ContractConformanceError("shared conformance vectors must be non-empty")
    vector_ids: set[str] = set()
    executed = 0
    for vector in vectors:
        if not isinstance(vector, dict):
            raise ContractConformanceError("conformance vector must be an object")
        vector_id = vector.get("id")
        if not isinstance(vector_id, str) or not vector_id or vector_id in vector_ids:
            raise ContractConformanceError(f"invalid/duplicate conformance vector {vector_id!r}")
        vector_ids.add(vector_id)
        expected = vector.get("expected")
        if expected not in {"accept", "reject"}:
            raise ContractConformanceError(f"{vector_id} expected must be accept/reject")
        accepted = False
        try:
            if vector.get("kind") == "raw_json":
                _strict_json(vector["payload"])
            elif vector.get("kind") == "schema_edge":
                record_name = vector["record"]
                payload = _base_record(record_name, schemas)
                mutation = vector["mutation"]
                op, value = mutation.split(":", 1)
                if op == "remove":
                    payload.pop(value, None)
                elif op == "null":
                    payload[value] = None
                elif op == "enum":
                    field, enum_value = value.split("=", 1)
                    payload[field] = enum_value
                else:
                    raise ValueError(f"unsupported mutation {op}")
                _validate_record(record_name, payload, schemas)
            else:
                raise ContractConformanceError(f"{vector_id} has unsupported kind")
            accepted = True
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            accepted = False
        if accepted != (expected == "accept"):
            raise ContractConformanceError(
                f"{vector_id} expected {expected} but got {'accept' if accepted else 'reject'}"
            )
        executed += 1

    source_paths = {
        "catalog": CATALOG,
        "schema_catalog": Path(sources["schema_catalog"]),
        "interface_registry": Path(sources["interface_registry"]),
    }
    source_digests = {
        key: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for key, relative in source_paths.items()
    }
    qualification_payload = {
        "contracts": sorted(by_name),
        "source_digests": source_digests,
        "vector_ids": sorted(vector_ids),
        "override_count": override_count,
        "authority_scope": "contract-conformance-only",
    }
    qualification_digest = hashlib.sha256(
        json.dumps(qualification_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return {
        "status": "valid",
        "contract_count": len(records),
        "override_count": override_count,
        "vector_count": len(vectors),
        "executed_vector_count": executed,
        "masterplan_binding": "VOL-003",
        "source_digests": source_digests,
        "qualification_digest": qualification_digest,
        "authority_scope": "contract-conformance-only",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except ContractConformanceError as exc:
        print(f"contract conformance: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "contract conformance: OK "
            f"({result['contract_count']} contracts, {result['vector_count']} vectors)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
