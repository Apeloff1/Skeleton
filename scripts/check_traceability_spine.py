#!/usr/bin/env python3
"""Validate the P2 requirements-to-runtime traceability spine.

The trace spine is intentionally derived. Machine registries may organize,
index, and add typed lineage to canonical sources, but they may not become a
parallel authority. This validator recomputes the important projections from
the masterplan/runtime contracts and fails closed on drift.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]

MASTER = Path("machine/ai_master_plan.json")
ACCOUNTABILITY = Path("machine/ai_build_accountability.json")
CAPABILITIES = Path("machine/ai_capabilities.json")
ENGINEERING = Path("machine/ai_engineering_pass.json")
STATE_TOPOLOGY = Path("machine/state_topology.json")
INTERFACES = Path("machine/capability_interfaces.json")
RUNTIME_SCHEMAS = Path("machine/ai_runtime_schemas.json")
CONTRACT_CONFORMANCE = Path("machine/contract_conformance.json")

REQUIREMENTS = Path("machine/requirement_registry.json")
CAPABILITY_TAXONOMY = Path("machine/capability_taxonomy.json")
NFR_REGISTRY = Path("machine/nfr_registry.json")
BEHAVIORS = Path("machine/behavior_specifications.json")
STATE_CATALOGUE = Path("machine/state_machine_catalogue.json")
INTERFACE_STANDARD = Path("machine/interface_standard.json")
SCHEMA_REGISTRY = Path("machine/schema_registry.json")
COMPATIBILITY = Path("machine/compatibility_model.json")
PROTOCOLS = Path("machine/protocol_registry.json")
MATURITY = Path("machine/maturity_registry.json")
MASTER_TRACE = Path("machine/master_traceability.json")


class TraceSpineError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TraceSpineError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise TraceSpineError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise TraceSpineError(f"{relative} must contain an object")
    return data


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise TraceSpineError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise TraceSpineError(f"invalid repository path: {value!r}")
    if pure.as_posix() != value:
        raise TraceSpineError(f"non-canonical repository path: {value!r}")
    return value


def _binding(
    master_by_ref: dict[str, dict[str, Any]],
    payload: dict[str, Any],
    volume_ref: str,
    gaps: Iterable[str],
) -> None:
    binding = payload.get("masterplan_binding")
    volume = master_by_ref.get(volume_ref)
    if not isinstance(binding, dict) or not isinstance(volume, dict):
        raise TraceSpineError(f"{volume_ref} masterplan binding is required")
    if binding.get("volume_ref") != volume_ref:
        raise TraceSpineError(f"{volume_ref} binding references wrong volume")
    if binding.get("title") != volume.get("title"):
        raise TraceSpineError(f"{volume_ref} binding title drift")
    required = binding.get("required_gap_texts")
    if not isinstance(required, list) or not required:
        raise TraceSpineError(f"{volume_ref} required_gap_texts must be non-empty")
    if set(required) != set(gaps):
        raise TraceSpineError(
            f"{volume_ref} trace registry must preserve the exact P2 gap set"
        )
    for gap in required:
        if gap not in volume.get("gaps", []):
            raise TraceSpineError(f"{volume_ref} masterplan gap drift: {gap!r}")


def _normalize_capability(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _fnv1a(value: str) -> str:
    digest = 0x811C9DC5
    for byte in value.encode("utf-8"):
        digest ^= byte
        digest = (digest * 0x01000193) & 0xFFFFFFFF
    return f"{digest:08X}"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()


def _nfr_id(value: str) -> str:
    return "NFR-" + _slug(value)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _normalize_watch_ref(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    item = value.strip()
    if item.startswith("planned:"):
        item = item[len("planned:") :]
    if not item or " " in item or "://" in item:
        return None
    return item


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise TraceSpineError(f"cannot load validator module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _enum_values(source: Path, class_name: str) -> list[str]:
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise TraceSpineError(f"cannot parse state source {source}: {exc}") from exc
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            values: list[str] = []
            for child in node.body:
                if (
                    isinstance(child, ast.Assign)
                    and len(child.targets) == 1
                    and isinstance(child.targets[0], ast.Name)
                    and isinstance(child.value, ast.Constant)
                    and isinstance(child.value.value, str)
                ):
                    values.append(child.value.value)
            if values:
                return values
    raise TraceSpineError(f"enum {class_name} not found in {source}")


def _validate_requirements(
    master: dict[str, Any],
    master_by_ref: dict[str, dict[str, Any]],
    registry: dict[str, Any],
) -> dict[str, Any]:
    _binding(
        master_by_ref,
        registry,
        "VOL-122",
        ("materialize canonical requirement IDs", "bind requirements to tests/evidence"),
    )
    rows = registry.get("requirements")
    if not isinstance(rows, list):
        raise TraceSpineError("requirement registry requirements must be a list")

    expected: list[dict[str, Any]] = []
    for volume in master.get("volumes", []):
        for index, text in enumerate(volume.get("requirements", []), start=1):
            expected.append(
                {
                    "requirement_id": f"REQ:{volume['key']}:{index:03d}",
                    "volume_ref": volume["key"],
                    "volume_title": volume["title"],
                    "ordinal": index,
                    "text": text,
                    "status": "specified",
                    "acceptance": {
                        "test_refs": list(volume.get("tests", [])),
                        "evaluation_refs": list(volume.get("evaluations", [])),
                        "evidence_refs": list(volume.get("evidence", [])),
                    },
                    "implementation_refs": list(volume.get("implementation_paths", [])),
                    "risk_context": list(volume.get("risks", [])),
                    "change_control": {
                        "accountability_id": volume.get("accountability_id"),
                        "signing_required": volume.get("signing_required") is True,
                    },
                }
            )

    if registry.get("requirement_count") != len(expected):
        raise TraceSpineError("requirement_count drift")
    if rows != expected:
        expected_by_id = {row["requirement_id"]: row for row in expected}
        actual_by_id = {
            row.get("requirement_id"): row for row in rows if isinstance(row, dict)
        }
        missing = sorted(set(expected_by_id) - set(actual_by_id))
        extra = sorted(set(actual_by_id) - set(expected_by_id))
        if missing or extra:
            raise TraceSpineError(
                f"requirement identity coverage drift missing={missing[:20]} extra={extra[:20]}"
            )
        first = next(
            (
                key
                for key in expected_by_id
                if expected_by_id[key] != actual_by_id[key]
            ),
            None,
        )
        raise TraceSpineError(f"requirement registry content drift at {first}")

    return {"requirement_count": len(expected)}


def _validate_capabilities(
    master: dict[str, Any],
    master_by_ref: dict[str, dict[str, Any]],
    runtime: dict[str, Any],
    taxonomy: dict[str, Any],
) -> dict[str, Any]:
    bindings = taxonomy.get("masterplan_bindings")
    if not isinstance(bindings, list):
        raise TraceSpineError("capability taxonomy masterplan_bindings must be a list")
    by_ref = {
        item.get("volume_ref"): {"masterplan_binding": item}
        for item in bindings
        if isinstance(item, dict)
    }
    _binding(
        master_by_ref,
        by_ref.get("VOL-113", {}),
        "VOL-113",
        ("unify capability descriptors", "bind runtime discovery to registry"),
    )
    _binding(
        master_by_ref,
        by_ref.get("VOL-124", {}),
        "VOL-124",
        ("normalize capability naming", "map all volumes to capability classes"),
    )

    concept_expected: dict[str, dict[str, Any]] = {}
    mappings_expected: list[dict[str, Any]] = []
    depth_passes = sorted(
        {volume.get("depth_pass") for volume in master.get("volumes", [])}
    )
    classes_expected = [
        {
            "class_id": "CAP-CLASS-ROOT",
            "name": "declared masterplan capabilities",
            "parent_id": None,
            "kind": "root",
        },
        *[
            {
                "class_id": f"CAP-CLASS-{depth}",
                "name": f"build depth {depth}",
                "parent_id": "CAP-CLASS-ROOT",
                "kind": "build-depth",
            }
            for depth in depth_passes
        ],
        {
            "class_id": "CAP-CLASS-RUNTIME",
            "name": "assembled runtime capabilities",
            "parent_id": "CAP-CLASS-ROOT",
            "kind": "runtime",
        },
    ]

    for volume in master.get("volumes", []):
        concept_ids: list[str] = []
        for raw in volume.get("capabilities", []):
            normalized = _normalize_capability(raw)
            concept_id = "CAP-CONCEPT-" + _fnv1a(normalized)
            concept_ids.append(concept_id)
            item = concept_expected.setdefault(
                concept_id,
                {
                    "concept_id": concept_id,
                    "canonical_name": normalized,
                    "declared_forms": set(),
                    "volume_refs": set(),
                },
            )
            if item["canonical_name"] != normalized:
                raise TraceSpineError(f"capability concept hash collision: {concept_id}")
            item["declared_forms"].add(raw)
            item["volume_refs"].add(volume["key"])
        mappings_expected.append(
            {
                "volume_ref": volume["key"],
                "depth_class_id": f"CAP-CLASS-{volume['depth_pass']}",
                "capability_concept_ids": sorted(concept_ids),
                "trace_capability_ids": [
                    f"CAP:{volume['key']}:{index:03d}"
                    for index, _ in enumerate(
                        volume.get("capabilities", []),
                        start=1,
                    )
                ],
            }
        )

    concepts_expected = [
        {
            "concept_id": item["concept_id"],
            "canonical_name": item["canonical_name"],
            "declared_forms": sorted(item["declared_forms"]),
            "volume_refs": sorted(item["volume_refs"]),
        }
        for item in concept_expected.values()
    ]
    concepts_expected.sort(key=lambda item: item["concept_id"])

    runtime_expected = [
        {
            "capability_id": item["capability_id"],
            "version": item["version"],
            "owner_plane": item["owner_plane"],
            "enabled": item["enabled"],
            "implementation_state": item["implementation_state"],
            "risk_class": item["risk_class"],
            "required_planes": list(item.get("required_planes", [])),
            "readiness_requirements": list(item.get("readiness_requirements", [])),
            "degraded_behavior": dict(item.get("degraded_behavior", {})),
            "source": "machine/ai_capabilities.json",
        }
        for item in runtime.get("capabilities", [])
    ]

    if taxonomy.get("classes") != classes_expected:
        raise TraceSpineError("capability taxonomy classes drift")
    if taxonomy.get("concepts") != concepts_expected:
        raise TraceSpineError("normalized capability concepts drift")
    if taxonomy.get("volume_mappings") != mappings_expected:
        raise TraceSpineError("capability taxonomy volume coverage drift")
    if taxonomy.get("runtime_descriptors") != runtime_expected:
        raise TraceSpineError("runtime capability descriptor drift")
    if len(mappings_expected) != len(master.get("volumes", [])):
        raise TraceSpineError("not every masterplan volume is capability-classified")

    return {
        "capability_concept_count": len(concepts_expected),
        "classified_volume_count": len(mappings_expected),
        "runtime_capability_count": len(runtime_expected),
    }


def _validate_behaviors(
    master_by_ref: dict[str, dict[str, Any]],
    runtime: dict[str, Any],
    registry: dict[str, Any],
    requirement_ids: set[str],
) -> dict[str, Any]:
    _binding(
        master_by_ref,
        registry,
        "VOL-126",
        ("define scenario schema", "bind behaviors to requirement IDs"),
    )
    expected: list[dict[str, Any]] = []
    for capability in runtime.get("capabilities", []):
        prefix = _slug(capability["capability_id"])
        expected.append(
            {
                "behavior_id": f"BEHAV-{prefix}-NORMAL",
                "capability_id": capability["capability_id"],
                "mode": "normal",
                "preconditions": list(capability.get("readiness_requirements", [])),
                "postconditions": [
                    "requested capability semantics are preserved",
                    "result status does not overstate unavailable/degraded dependencies",
                ],
                "forbidden_outcomes": [
                    "silent fallback to weaker capability guarantees",
                    "enabled=true treated as ready without readiness proof",
                ],
                "requirement_ids": [
                    "REQ:VOL-113:001",
                    "REQ:VOL-113:002",
                    "REQ:VOL-126:001",
                    "REQ:VOL-126:002",
                ],
            }
        )
        for failure, action in capability.get("degraded_behavior", {}).items():
            expected.append(
                {
                    "behavior_id": f"BEHAV-{prefix}-DEG-{_slug(failure)}",
                    "capability_id": capability["capability_id"],
                    "mode": "degraded",
                    "trigger": failure,
                    "required_behavior": action,
                    "forbidden_outcomes": [
                        "claiming unavailable dependency succeeded",
                        "silent reroute into broader authority or weaker verification",
                    ],
                    "requirement_ids": [
                        "REQ:VOL-113:003",
                        "REQ:VOL-126:001",
                        "REQ:VOL-126:002",
                    ],
                }
            )
    actual = registry.get("behavior_specs")
    if actual != expected:
        raise TraceSpineError("behavior specification derivation drift")
    for item in expected:
        missing = sorted(set(item.get("requirement_ids", [])) - requirement_ids)
        if missing:
            raise TraceSpineError(
                f"{item['behavior_id']} references unknown requirements: {missing}"
            )
    return {"behavior_count": len(expected)}


def _validate_states(
    root: Path,
    master_by_ref: dict[str, dict[str, Any]],
    topology: dict[str, Any],
    schemas: dict[str, Any],
    catalogue: dict[str, Any],
) -> dict[str, Any]:
    _binding(
        master_by_ref,
        catalogue,
        "VOL-127",
        ("extract existing lifecycle machines", "bind transition tests"),
    )
    expected = [
        {
            "machine_id": "STATE-OPERATION",
            "owner": "orchestration",
            "version": 1,
            "source": "skeleton/contracts/operation.py",
            "enum_symbol": "OperationState",
            "transition_symbol": "_ALLOWED_TRANSITIONS",
            "terminal_symbol": "TERMINAL_OPERATION_STATES",
            "schema_enum": "OperationState",
            "test_refs": [
                "skeleton/testing/test_operation_runtime.py",
                "planned:skeleton/testing/test_state_machine_catalogue.py",
            ],
            "recovery_states": [
                "retrying",
                "degraded",
                "waiting_for_tool",
                "waiting_for_user",
            ],
        },
        {
            "machine_id": "STATE-AI-EXECUTION",
            "owner": "orchestration",
            "version": 1,
            "source": "skeleton/contracts/ai_execution.py",
            "enum_symbol": "ExecutionState",
            "transition_symbol": "_ALLOWED_EXECUTION_TRANSITIONS",
            "terminal_symbol": "TERMINAL_EXECUTION_STATES",
            "schema_enum": "ExecutionState",
            "test_refs": [
                "skeleton/testing/test_engine_execution_service.py",
                "skeleton/testing/test_engine_execution_coordinator.py",
                "planned:skeleton/testing/test_state_machine_catalogue.py",
            ],
            "recovery_states": [
                "repairing",
                "degraded",
                "checkpointing",
                "waiting_for_tool_authority",
                "waiting_for_user",
            ],
        },
    ]
    if catalogue.get("state_machines") != expected:
        raise TraceSpineError("state machine catalogue definition drift")

    enums = schemas.get("enums", {})
    for machine in expected:
        source = root / machine["source"]
        text = source.read_text(encoding="utf-8")
        for symbol in (
            machine["transition_symbol"],
            machine["terminal_symbol"],
        ):
            if symbol not in text:
                raise TraceSpineError(
                    f"{machine['machine_id']} source lacks {symbol}"
                )
        source_values = _enum_values(source, machine["enum_symbol"])
        schema_values = enums.get(machine["schema_enum"])
        if source_values != schema_values:
            raise TraceSpineError(
                f"{machine['machine_id']} source/schema enum drift"
            )
        if not set(machine["recovery_states"]) <= set(source_values):
            raise TraceSpineError(
                f"{machine['machine_id']} recovery states are not declared states"
            )

    domains_expected = [
        {
            "domain_id": item["id"],
            "owner_plane": item.get("owner_plane"),
            "authority": item.get("authority"),
            "status": item.get("status"),
        }
        for item in topology.get("state_domains", [])
    ]
    if catalogue.get("state_domain_refs") != domains_expected:
        raise TraceSpineError("state-domain catalogue drift")

    return {
        "state_machine_count": len(expected),
        "state_domain_count": len(domains_expected),
    }


def _validate_interfaces(
    master_by_ref: dict[str, dict[str, Any]],
    interfaces: dict[str, Any],
    standard: dict[str, Any],
    schema_names: set[str],
) -> dict[str, Any]:
    _binding(
        master_by_ref,
        standard,
        "VOL-128",
        ("codify interface lint rules", "bind public contracts to schema registry"),
    )
    rules = standard.get("rules")
    if not isinstance(rules, list) or len(rules) != 6:
        raise TraceSpineError("interface lint rule set drift")
    if any(item.get("severity") != "blocking" for item in rules):
        raise TraceSpineError("all interface design rules must remain blocking")

    expected = [
        {
            "interface_id": item["id"],
            "relation": item["relation"],
            "source_plane": item["source_plane"],
            "target_plane": item["target_plane"],
            "contract_surface": list(item.get("target_contract_surface", [])),
            "failure_contract": item.get("target_failure_contract"),
            "ownership_rule": item.get("ownership_rule"),
            "status": item.get("status"),
        }
        for item in interfaces.get("entries", [])
    ]
    if standard.get("interface_bindings") != expected:
        raise TraceSpineError("interface-standard binding drift")
    for item in expected:
        if not item["contract_surface"]:
            raise TraceSpineError(f"{item['interface_id']} has empty contract surface")
        if not isinstance(item["failure_contract"], str) or not item["failure_contract"]:
            raise TraceSpineError(f"{item['interface_id']} lacks failure contract")
        # Named canonical runtime records are schema-bound; prose surface labels
        # remain valid interface semantics without being mistaken for schema IDs.
        canonical = {
            value for value in item["contract_surface"] if value in schema_names
        }
        if any(value.startswith("SCHEMA-") for value in item["contract_surface"]):
            raise TraceSpineError(
                f"{item['interface_id']} must use record names, not local schema aliases"
            )
        _ = canonical
    return {"interface_count": len(expected)}


def _validate_schemas(
    master_by_ref: dict[str, dict[str, Any]],
    runtime_schemas: dict[str, Any],
    conformance: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    _binding(
        master_by_ref,
        registry,
        "VOL-129",
        ("inventory serialized contracts", "materialize compatibility checker"),
    )
    conformance_by_name = {
        item["contract"]: item
        for item in conformance.get("entries", [])
        if isinstance(item, dict) and isinstance(item.get("contract"), str)
    }
    expected = []
    for name, record in runtime_schemas.get("records", {}).items():
        trace = conformance_by_name.get(name)
        if trace is None:
            raise TraceSpineError(f"schema {name} lacks contract conformance lineage")
        expected.append(
            {
                "schema_id": f"SCHEMA-{name}",
                "record_name": name,
                "version": record.get("schema_version"),
                "owner_plane": record.get("owner_plane"),
                "compatibility_mode": "backward",
                "canonical_serialization": (
                    "machine/ai_runtime_schemas.json#conventions/canonical_json"
                ),
                "producer_plane": trace.get("producer_plane"),
                "consumer_planes": list(trace.get("consumer_planes", [])),
                "source": "machine/ai_runtime_schemas.json",
                "migration_required_for_breaking_change": True,
            }
        )
    if registry.get("schemas") != expected:
        raise TraceSpineError("schema registry derivation drift")
    return {
        "schema_count": len(expected),
        "schema_names": {item["record_name"] for item in expected},
        "schemas": expected,
    }


def _validate_compatibility(
    master_by_ref: dict[str, dict[str, Any]],
    schemas: list[dict[str, Any]],
    interfaces: dict[str, Any],
    model: dict[str, Any],
) -> dict[str, Any]:
    _binding(
        master_by_ref,
        model,
        "VOL-130",
        ("bind schema/API versions to matrix", "define support window policy"),
    )
    policy = model.get("support_window_policy")
    if not isinstance(policy, dict):
        raise TraceSpineError("compatibility support_window_policy is required")
    if policy.get("default_supported_versions") != 2:
        raise TraceSpineError("default compatibility support window drift")
    for key in ("rule", "breaking_change_rule", "rollback_rule"):
        if not isinstance(policy.get(key), str) or not policy[key]:
            raise TraceSpineError(f"compatibility policy lacks {key}")

    expected_schemas = [
        {
            "schema_id": item["schema_id"],
            "current_version": item["version"],
            "supported_versions": [item["version"]],
            "reader_writer_mode": item["compatibility_mode"],
            "producer_plane": item["producer_plane"],
            "consumer_planes": list(item["consumer_planes"]),
            "migration_required_for_breaking_change": True,
        }
        for item in schemas
    ]
    if model.get("schema_matrix") != expected_schemas:
        raise TraceSpineError("schema compatibility matrix drift")

    expected_interfaces = [
        {
            "interface_id": item["id"],
            "status": item.get("status"),
            "producer": item["source_plane"],
            "consumer": item["target_plane"],
            "compatibility_semantics": (
                "contract-surface additive unless schema registry marks "
                "versioned breaking change"
            ),
            "rollback_required": True,
        }
        for item in interfaces.get("entries", [])
    ]
    if model.get("interface_matrix") != expected_interfaces:
        raise TraceSpineError("interface compatibility matrix drift")
    return {
        "compatibility_schema_count": len(expected_schemas),
        "compatibility_interface_count": len(expected_interfaces),
    }


def _validate_protocols(
    root: Path,
    master_by_ref: dict[str, dict[str, Any]],
    registry: dict[str, Any],
) -> dict[str, Any]:
    _binding(
        master_by_ref,
        registry,
        "VOL-131",
        ("unify protocol envelopes", "bind protocols to tracing"),
    )
    canonical = registry.get("canonical_envelope")
    if not isinstance(canonical, dict):
        raise TraceSpineError("canonical protocol envelope descriptor is required")
    source = root / _repo_path(canonical.get("source"))
    mirror = root / _repo_path(canonical.get("mirror"))
    if not source.is_file() or not mirror.is_file():
        raise TraceSpineError("canonical protocol source/mirror is missing")
    if source.read_bytes() != mirror.read_bytes():
        raise TraceSpineError("canonical protocol AI mirror drift")

    source_text = source.read_text(encoding="utf-8")
    for symbol in (
        "class ProtocolEnvelope",
        "class ProtocolReplayGuard",
        "class RetryClass",
        "class UnknownOutcomePolicy",
        "PROTOCOL_ENVELOPE_VERSION",
    ):
        if symbol not in source_text:
            raise TraceSpineError(f"canonical protocol source lacks {symbol}")

    required_fields = canonical.get("required_fields")
    expected_fields = [
        "protocol",
        "protocol_version",
        "message_id",
        "kind",
        "sender",
        "recipient",
        "operation_id",
        "correlation_id",
        "causation_id",
        "trace_id",
        "span_id",
        "deadline_utc",
        "idempotency_key",
        "attempt",
        "retry_class",
        "unknown_outcome_policy",
        "payload",
    ]
    if required_fields != expected_fields:
        raise TraceSpineError("canonical protocol field set drift")

    export_paths = [
        root / "skeleton/contracts/__init__.py",
        root / "skeleton/ai/runtime/contracts/__init__.py",
    ]
    if export_paths[0].read_bytes() != export_paths[1].read_bytes():
        raise TraceSpineError("contract package export mirror drift")
    exports = export_paths[0].read_text(encoding="utf-8")
    for symbol in (
        "ProtocolEnvelope",
        "ProtocolReplayGuard",
        "RetryClass",
        "UnknownOutcomePolicy",
    ):
        if symbol not in exports:
            raise TraceSpineError(f"contract exports lack {symbol}")

    protocols = registry.get("protocols")
    if not isinstance(protocols, list) or len(protocols) != 4:
        raise TraceSpineError("internal protocol registry coverage drift")
    ids = [item.get("protocol_id") for item in protocols if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        raise TraceSpineError("duplicate internal protocol ID")
    for item in protocols:
        path = root / _repo_path(item.get("source"))
        if not path.is_file():
            raise TraceSpineError(
                f"{item.get('protocol_id')} source is missing: {item.get('source')}"
            )
        if item.get("status") == "existing-adapter":
            if item.get("adapter_required") is not True:
                raise TraceSpineError(
                    f"{item.get('protocol_id')} must remain adapter-tracked"
                )
            missing = item.get("missing_canonical_fields")
            if not isinstance(missing, list) or not missing:
                raise TraceSpineError(
                    f"{item.get('protocol_id')} lacks migration gap inventory"
                )
    return {"protocol_count": len(protocols)}


def _expected_maturity_entry(
    volume: dict[str, Any],
    accountability: dict[str, Any],
) -> dict[str, Any]:
    evidence_input = {
        "volume_ref": volume["key"],
        "implementation_status": volume.get("implementation_status"),
        "status": volume.get("status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "evidence": list(volume.get("evidence", [])),
        "tests": list(volume.get("tests", [])),
        "evaluations": list(volume.get("evaluations", [])),
        "accountability": {
            "id": accountability.get("id"),
            "status": accountability.get("status"),
            "checkbox": accountability.get("checkbox"),
            "implementation_signoff": accountability.get("implementation_signoff"),
            "verification_signoff": accountability.get("verification_signoff"),
            "evidence": list(accountability.get("evidence", [])),
            "history": list(accountability.get("history", [])),
        },
    }
    watch = {"machine/ai_master_plan.json", "machine/ai_build_accountability.json"}
    for raw in (
        list(volume.get("implementation_paths", []))
        + list(volume.get("tests", []))
        + list(volume.get("evaluations", []))
        + list(volume.get("evidence", []))
    ):
        normalized = _normalize_watch_ref(raw)
        if normalized:
            watch.add(normalized)
    return {
        "volume_ref": volume["key"],
        "accountability_id": volume.get("accountability_id"),
        "current_status": volume.get("status"),
        "current_implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "signing_required": volume.get("signing_required"),
        "evidence_digest_algorithm": "sha256-canonical-json",
        "evidence_digest": _digest(evidence_input),
        "evidence_input": evidence_input,
        "invalidation": {
            "status": "valid_at_registry_generation",
            "watch_refs": sorted(watch),
            "triggers": [
                "masterplan requirement/risk/gap change",
                "implementation path change",
                "test/evaluation contract change",
                "accountability evidence/signoff change",
                "referenced evidence identity change",
            ],
            "rule": (
                "Any matching change invalidates the cached maturity projection "
                "until the evidence digest is recomputed and required gates/signoff "
                "are revalidated."
            ),
        },
    }


def _validate_maturity(
    master: dict[str, Any],
    master_by_ref: dict[str, dict[str, Any]],
    accountability: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    _binding(
        master_by_ref,
        registry,
        "VOL-125",
        ("bind maturity to evidence digests", "add automatic invalidation triggers"),
    )
    account_by_id = {
        item.get("id"): item
        for item in accountability.get("records", [])
        if isinstance(item, dict)
    }
    expected: list[dict[str, Any]] = []
    for volume in master.get("volumes", []):
        account = account_by_id.get(volume.get("accountability_id"))
        if not isinstance(account, dict):
            raise TraceSpineError(
                f"{volume.get('key')} lacks accountability record "
                f"{volume.get('accountability_id')}"
            )
        expected.append(_expected_maturity_entry(volume, account))
    if registry.get("entry_count") != len(expected):
        raise TraceSpineError("maturity entry_count drift")
    actual = registry.get("entries")
    if actual != expected:
        expected_by_ref = {item["volume_ref"]: item for item in expected}
        actual_by_ref = {
            item.get("volume_ref"): item
            for item in actual or []
            if isinstance(item, dict)
        }
        first = next(
            (
                ref
                for ref in expected_by_ref
                if actual_by_ref.get(ref) != expected_by_ref[ref]
            ),
            None,
        )
        raise TraceSpineError(f"maturity evidence digest/watch drift at {first}")
    return {"maturity_entry_count": len(expected)}


def _path_matches(changed: str, watched: str) -> bool:
    value = watched.rstrip("/")
    if changed == value:
        return True
    # Directory-like refs are prefixes. File-like refs require exact matching.
    tail = PurePosixPath(value).name
    if "." not in tail:
        return changed.startswith(value + "/")
    return False


def _impact(
    root: Path,
    changed_files: list[str],
    master_impact: dict[str, Any],
    maturity: dict[str, Any],
    authority_paths: set[str],
) -> dict[str, Any]:
    changed = [_repo_path(item) for item in changed_files]
    maturity_hits: dict[str, list[str]] = {}
    for path in changed:
        refs = sorted(
            {
                entry["volume_ref"]
                for entry in maturity.get("entries", [])
                if any(
                    _path_matches(path, watched)
                    for watched in entry.get("invalidation", {}).get("watch_refs", [])
                )
            }
        )
        if refs:
            maturity_hits[path] = refs

    control_hits = sorted(path for path in changed if path in authority_paths)
    impacted = set(master_impact.get("impacted_volume_refs", []))
    for refs in maturity_hits.values():
        impacted.update(refs)

    return {
        "changed_files": changed,
        "master_trace_impacted_volume_refs": master_impact.get(
            "impacted_volume_refs", []
        ),
        "maturity_invalidated_volume_refs": sorted(
            {ref for refs in maturity_hits.values() for ref in refs}
        ),
        "maturity_invalidation_by_file": maturity_hits,
        "trace_authority_files_changed": control_hits,
        "combined_impacted_volume_refs": sorted(impacted),
        "unmapped_changed_files": master_impact.get("unmapped_changed_files", []),
    }


def validate(
    root: Path = ROOT,
    *,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    root = root.resolve()

    master = _load(root, MASTER)
    accountability = _load(root, ACCOUNTABILITY)
    runtime_capabilities = _load(root, CAPABILITIES)
    engineering = _load(root, ENGINEERING)
    topology = _load(root, STATE_TOPOLOGY)
    interfaces = _load(root, INTERFACES)
    runtime_schemas = _load(root, RUNTIME_SCHEMAS)
    conformance = _load(root, CONTRACT_CONFORMANCE)

    requirements = _load(root, REQUIREMENTS)
    taxonomy = _load(root, CAPABILITY_TAXONOMY)
    nfr_registry = _load(root, NFR_REGISTRY)
    behaviors = _load(root, BEHAVIORS)
    states = _load(root, STATE_CATALOGUE)
    standard = _load(root, INTERFACE_STANDARD)
    schemas = _load(root, SCHEMA_REGISTRY)
    compatibility = _load(root, COMPATIBILITY)
    protocols = _load(root, PROTOCOLS)
    maturity = _load(root, MATURITY)
    _ = _load(root, MASTER_TRACE)

    master_by_ref = {
        item.get("key"): item
        for item in master.get("volumes", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    if len(master_by_ref) != 421:
        raise TraceSpineError(
            f"trace spine expects frozen 421-volume masterplan, got {len(master_by_ref)}"
        )

    result: dict[str, Any] = {"status": "valid"}
    req_result = _validate_requirements(master, master_by_ref, requirements)
    result.update(req_result)
    requirement_ids = {
        item["requirement_id"] for item in requirements["requirements"]
    }

    result.update(
        _validate_capabilities(
            master,
            master_by_ref,
            runtime_capabilities,
            taxonomy,
        )
    )

    nfr_module = _load_module(
        "check_nfr_registry",
        root / "scripts" / "check_nfr_registry.py",
    )
    try:
        nfr_result = nfr_module.validate(root)
    except Exception as exc:
        raise TraceSpineError(f"NFR registry validation failed: {exc}") from exc
    result["nfr_count"] = nfr_result["nfr_count"]
    result["nfr_work_package_count"] = nfr_result["work_package_count"]

    result.update(
        _validate_behaviors(
            master_by_ref,
            runtime_capabilities,
            behaviors,
            requirement_ids,
        )
    )
    result.update(
        _validate_states(
            root,
            master_by_ref,
            topology,
            runtime_schemas,
            states,
        )
    )

    schema_result = _validate_schemas(
        master_by_ref,
        runtime_schemas,
        conformance,
        schemas,
    )
    result["schema_count"] = schema_result["schema_count"]
    result.update(
        _validate_interfaces(
            master_by_ref,
            interfaces,
            standard,
            schema_result["schema_names"],
        )
    )
    result.update(
        _validate_compatibility(
            master_by_ref,
            schema_result["schemas"],
            interfaces,
            compatibility,
        )
    )
    result.update(_validate_protocols(root, master_by_ref, protocols))
    result.update(
        _validate_maturity(
            master,
            master_by_ref,
            accountability,
            maturity,
        )
    )

    trace_module = _load_module(
        "check_master_traceability",
        root / "scripts" / "check_master_traceability.py",
    )
    try:
        trace_result = trace_module.validate(root)
    except Exception as exc:
        raise TraceSpineError(f"master trace graph validation failed: {exc}") from exc
    result["master_trace_node_count"] = trace_result["node_count"]
    result["master_trace_edge_count"] = trace_result["edge_count"]
    result["master_trace_volume_count"] = trace_result["volume_count"]

    if trace_result["requirement_count"] != result["requirement_count"]:
        raise TraceSpineError(
            "requirement registry count disagrees with sharded master trace graph"
        )

    if changed_files:
        try:
            master_impact = trace_module.impact(root, changed_files)
        except Exception as exc:
            raise TraceSpineError(f"master trace impact resolution failed: {exc}") from exc
        authority_paths = {
            str(REQUIREMENTS),
            str(CAPABILITY_TAXONOMY),
            str(NFR_REGISTRY),
            str(BEHAVIORS),
            str(STATE_CATALOGUE),
            str(INTERFACE_STANDARD),
            str(SCHEMA_REGISTRY),
            str(COMPATIBILITY),
            str(PROTOCOLS),
            str(MATURITY),
            str(MASTER_TRACE),
            "scripts/check_traceability_spine.py",
            "scripts/check_master_traceability.py",
            "scripts/check_nfr_registry.py",
        }
        result["impact"] = _impact(
            root,
            changed_files,
            master_impact,
            maturity,
            authority_paths,
        )

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(
            Path(args.repo_root),
            changed_files=args.changed_file or None,
        )
    except TraceSpineError as exc:
        print(f"traceability spine: FAIL: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "traceability spine: OK "
            f"({result['requirement_count']} requirements, "
            f"{result['capability_concept_count']} capability concepts, "
            f"{result['nfr_count']} NFRs, "
            f"{result['schema_count']} schemas, "
            f"{result['master_trace_node_count']} trace nodes)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
