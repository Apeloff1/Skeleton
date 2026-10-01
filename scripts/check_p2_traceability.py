#!/usr/bin/env python3
"""Fail-closed validation and change-impact analysis for P2 traceability."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
TRACE_REFS = (
    "VOL-112",
    "VOL-113",
    "VOL-122",
    "VOL-123",
    "VOL-124",
    "VOL-125",
    "VOL-126",
    "VOL-127",
    "VOL-128",
    "VOL-129",
    "VOL-130",
    "VOL-131",
)

AUTHORITY_BINDINGS = {
    "machine/master_traceability.json": (
        "VOL-112",
        "Master Traceability Matrix",
        ("materialize canonical trace graph", "bind PR impact checks to trace edges"),
    ),
    "machine/capability_registry.json": (
        "VOL-113",
        "Capability Map",
        ("unify capability descriptors", "bind runtime discovery to registry"),
    ),
    "machine/requirement_registry.json": (
        "VOL-122",
        "Requirements Engineering",
        ("materialize canonical requirement IDs", "bind requirements to tests/evidence"),
    ),
    "machine/nfr_registry.json": (
        "VOL-123",
        "Non-Functional Requirements",
        ("bind all production claims to NFR IDs", "materialize measurement harnesses"),
    ),
    "machine/capability_taxonomy.json": (
        "VOL-124",
        "Capability Taxonomy",
        ("normalize capability naming", "map all volumes to capability classes"),
    ),
    "machine/capability_maturity.json": (
        "VOL-125",
        "Capability Maturity Model",
        ("bind maturity to evidence digests", "add automatic invalidation triggers"),
    ),
    "machine/behavior_specifications.json": (
        "VOL-126",
        "Behavior Specifications",
        ("define scenario schema", "bind behaviors to requirement IDs"),
    ),
    "machine/state_machine_catalogue.json": (
        "VOL-127",
        "State Machine Catalogue",
        ("extract existing lifecycle machines", "bind transition tests"),
    ),
    "machine/interface_standard.json": (
        "VOL-128",
        "Interface Design Standard",
        ("codify interface lint rules", "bind public contracts to schema registry"),
    ),
    "machine/schema_registry.json": (
        "VOL-129",
        "Schema Registry",
        ("inventory serialized contracts", "materialize compatibility checker"),
    ),
    "machine/compatibility_model.json": (
        "VOL-130",
        "Compatibility Model",
        ("bind schema/API versions to matrix", "define support window policy"),
    ),
    "machine/internal_protocols.json": (
        "VOL-131",
        "Internal Protocols",
        ("unify protocol envelopes", "bind protocols to tracing"),
    ),
}


class TraceabilityError(RuntimeError):
    pass


def _load(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TraceabilityError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise TraceabilityError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TraceabilityError(f"{relative} must contain a JSON object")
    return payload


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise TraceabilityError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise TraceabilityError(f"invalid repository path: {value!r}")
    if pure.as_posix() != value:
        raise TraceabilityError(f"non-canonical repository path: {value!r}")
    return value


def _slug(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:80]


def _assert_masterplan_binding(
    payload: dict[str, Any],
    master_by_ref: dict[str, dict[str, Any]],
    relative: str,
) -> None:
    expected_ref, expected_title, expected_gaps = AUTHORITY_BINDINGS[relative]
    binding = payload.get("masterplan_binding")
    if not isinstance(binding, dict):
        raise TraceabilityError(f"{relative} lacks masterplan_binding")
    if binding.get("volume_ref") != expected_ref:
        raise TraceabilityError(
            f"{relative} must bind {expected_ref}, got {binding.get('volume_ref')!r}"
        )
    volume = master_by_ref.get(expected_ref)
    if not isinstance(volume, dict):
        raise TraceabilityError(f"masterplan missing {expected_ref}")
    if binding.get("title") != volume.get("title") or binding.get("title") != expected_title:
        raise TraceabilityError(f"{relative} masterplan title drift for {expected_ref}")
    gaps = binding.get("required_gap_texts")
    if gaps != list(expected_gaps):
        raise TraceabilityError(f"{relative} must preserve exact masterplan gap binding")
    for gap in gaps:
        if gap not in volume.get("gaps", []):
            raise TraceabilityError(
                f"{relative} references stale masterplan gap {expected_ref}: {gap!r}"
            )


def _validate_requirements(
    root: Path,
    master_by_ref: dict[str, dict[str, Any]],
    registry: dict[str, Any],
) -> set[str]:
    entries = registry.get("requirements")
    if not isinstance(entries, list) or not entries:
        raise TraceabilityError("requirement registry must be non-empty")

    expected: dict[str, tuple[str, str, str]] = {}
    for ref in TRACE_REFS:
        volume = master_by_ref[ref]
        for index, text in enumerate(volume.get("requirements", []), start=1):
            req_id = f"REQ-{ref}-R{index:02d}"
            expected[req_id] = (ref, "masterplan.requirements", text)
        for index, text in enumerate(volume.get("gaps", []), start=1):
            req_id = f"REQ-{ref}-G{index:02d}"
            expected[req_id] = (ref, "masterplan.gaps", text)

    actual: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict):
            raise TraceabilityError("requirement entry must be an object")
        req_id = item.get("id")
        if not isinstance(req_id, str) or not req_id:
            raise TraceabilityError("requirement entry missing id")
        if req_id in actual:
            raise TraceabilityError(f"duplicate requirement id: {req_id}")
        actual[req_id] = item

    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise TraceabilityError(
            f"requirement registry coverage drift; missing={missing}, extra={extra}"
        )

    for req_id, (ref, source, text) in expected.items():
        item = actual[req_id]
        if item.get("volume_ref") != ref:
            raise TraceabilityError(f"{req_id} volume_ref drift")
        if item.get("source") != source:
            raise TraceabilityError(f"{req_id} source drift")
        if item.get("text") != text:
            raise TraceabilityError(f"{req_id} text drift from masterplan")
        kind = item.get("kind")
        if ref == "VOL-123" and not str(kind).startswith("non_functional"):
            raise TraceabilityError(f"{req_id} must remain explicitly non-functional")
        refs = item.get("acceptance_refs")
        if not isinstance(refs, list) or not refs:
            raise TraceabilityError(f"{req_id} lacks acceptance refs")
        for acceptance in refs:
            path = _repo_path(acceptance)
            if not (root / path).is_file():
                raise TraceabilityError(
                    f"{req_id} acceptance ref does not exist: {path}"
                )
    return set(actual)


def _validate_taxonomy(
    root: Path,
    master: dict[str, Any],
    taxonomy: dict[str, Any],
) -> dict[str, str]:
    if taxonomy.get("source_git_blob_sha") != _git_blob_sha(
        root / "machine/ai_master_plan.json"
    ):
        raise TraceabilityError("capability taxonomy masterplan digest is stale")

    terms = sorted(
        {
            str(capability).strip()
            for volume in master.get("volumes", [])
            for capability in volume.get("capabilities", [])
            if str(capability).strip()
        }
    )
    expected = {
        term: f"CAP-{index:04d}" for index, term in enumerate(terms, start=1)
    }
    capabilities = taxonomy.get("capabilities")
    if not isinstance(capabilities, list):
        raise TraceabilityError("capability taxonomy capabilities must be a list")
    seen: dict[str, str] = {}
    ids: set[str] = set()
    for item in capabilities:
        if not isinstance(item, dict):
            raise TraceabilityError("capability taxonomy entry must be an object")
        name = item.get("name")
        cap_id = item.get("id")
        if name in seen or cap_id in ids:
            raise TraceabilityError("duplicate capability name or id")
        seen[name] = cap_id
        ids.add(cap_id)
        if item.get("normalized_name") != _slug(str(name)):
            raise TraceabilityError(f"capability normalized name drift: {name!r}")
    if seen != expected:
        raise TraceabilityError("capability taxonomy is not deterministic from masterplan")

    volume_map = taxonomy.get("volume_map")
    if not isinstance(volume_map, list):
        raise TraceabilityError("capability taxonomy volume_map must be a list")
    by_ref: dict[str, dict[str, Any]] = {}
    for item in volume_map:
        if not isinstance(item, dict) or not isinstance(item.get("volume_ref"), str):
            raise TraceabilityError("invalid capability volume mapping")
        ref = item["volume_ref"]
        if ref in by_ref:
            raise TraceabilityError(f"duplicate capability volume mapping: {ref}")
        by_ref[ref] = item
    master_volumes = {v["key"]: v for v in master.get("volumes", [])}
    if set(by_ref) != set(master_volumes):
        raise TraceabilityError("capability taxonomy must map every masterplan volume")
    for ref, volume in master_volumes.items():
        wanted = [expected[str(cap).strip()] for cap in volume.get("capabilities", [])]
        if by_ref[ref].get("capability_ids") != wanted:
            raise TraceabilityError(f"{ref} capability mapping drift")
        if not isinstance(by_ref[ref].get("class_id"), str):
            raise TraceabilityError(f"{ref} lacks capability class")
    return expected


def _runtime_cap_id(plane: str) -> str:
    return "RUNTIME-" + _slug(plane).upper().replace("-", "_")


def _validate_runtime_capabilities(
    root: Path,
    interfaces: dict[str, Any],
    registry: dict[str, Any],
) -> None:
    if registry.get("source_git_blob_sha") != _git_blob_sha(
        root / "machine/capability_interfaces.json"
    ):
        raise TraceabilityError("runtime capability registry source digest is stale")
    edges = interfaces.get("entries", [])
    planes = sorted(
        {
            plane
            for edge in edges
            for plane in (edge.get("source_plane"), edge.get("target_plane"))
            if isinstance(plane, str) and plane
        }
    )
    entries = registry.get("capabilities")
    if not isinstance(entries, list):
        raise TraceabilityError("runtime capability descriptors must be a list")
    by_plane = {item.get("plane"): item for item in entries if isinstance(item, dict)}
    if set(by_plane) != set(planes) or len(by_plane) != len(entries):
        raise TraceabilityError("runtime capability plane coverage drift")
    for plane in planes:
        item = by_plane[plane]
        incoming = [
            edge
            for edge in edges
            if edge.get("target_plane") == plane
            and edge.get("relation") == "runtime_dependency"
        ]
        outgoing = [
            edge
            for edge in edges
            if edge.get("source_plane") == plane
            and edge.get("relation") == "runtime_dependency"
        ]
        owners = sorted(
            {
                edge.get("target_owner")
                for edge in edges
                if edge.get("target_plane") == plane
                and isinstance(edge.get("target_owner"), str)
            }
        )
        refs = sorted(
            edge["id"]
            for edge in edges
            if edge.get("source_plane") == plane or edge.get("target_plane") == plane
        )
        if item.get("id") != _runtime_cap_id(plane):
            raise TraceabilityError(f"{plane} runtime capability id drift")
        if item.get("status") != "present":
            raise TraceabilityError(f"{plane} may not advertise unsupported availability")
        if item.get("owners") != owners:
            raise TraceabilityError(f"{plane} owner descriptor drift")
        if item.get("dependency_planes") != sorted(
            {edge["target_plane"] for edge in outgoing}
        ):
            raise TraceabilityError(f"{plane} dependency descriptor drift")
        if item.get("incoming_consumer_planes") != sorted(
            {edge["source_plane"] for edge in incoming}
        ):
            raise TraceabilityError(f"{plane} incoming consumer descriptor drift")
        if item.get("interface_edge_refs") != refs:
            raise TraceabilityError(f"{plane} interface edge descriptor drift")


def _validate_maturity(
    root: Path,
    master_by_ref: dict[str, dict[str, Any]],
    accountability: dict[str, Any],
    maturity: dict[str, Any],
) -> None:
    sources = maturity.get("sources", {})
    for key, relative in (
        ("master_plan", "machine/ai_master_plan.json"),
        ("accountability", "machine/ai_build_accountability.json"),
    ):
        source = sources.get(key)
        if not isinstance(source, dict) or source.get("path") != relative:
            raise TraceabilityError(f"capability maturity source {key} drift")
        if source.get("git_blob_sha") != _git_blob_sha(root / relative):
            raise TraceabilityError(f"capability maturity source {key} digest is stale")

    acc_by_id = {
        item.get("id"): item
        for item in accountability.get("records", [])
        if isinstance(item, dict)
    }
    entries = maturity.get("volumes")
    if not isinstance(entries, list):
        raise TraceabilityError("capability maturity volumes must be a list")
    by_ref = {item.get("volume_ref"): item for item in entries if isinstance(item, dict)}
    if set(by_ref) != set(TRACE_REFS) or len(by_ref) != len(entries):
        raise TraceabilityError("capability maturity must cover P2 trace volumes exactly")
    for ref in TRACE_REFS:
        volume = master_by_ref[ref]
        acc = acc_by_id.get(volume.get("accountability_id"))
        if not isinstance(acc, dict):
            raise TraceabilityError(f"{ref} accountability record missing")
        item = by_ref[ref]
        if item.get("accountability_id") != volume.get("accountability_id"):
            raise TraceabilityError(f"{ref} accountability id drift")
        if item.get("masterplan_status") != volume.get("implementation_status"):
            raise TraceabilityError(f"{ref} masterplan maturity drift")
        if item.get("accountability_status") != acc.get("status"):
            raise TraceabilityError(f"{ref} accountability maturity drift")
        if item.get("checkbox") != acc.get("checkbox"):
            raise TraceabilityError(f"{ref} checkbox drift")
        if item.get("implementation_signed") != acc.get(
            "implementation_signoff", {}
        ).get("signed"):
            raise TraceabilityError(f"{ref} implementation signoff drift")
        if item.get("verification_signed") != acc.get(
            "verification_signoff", {}
        ).get("signed"):
            raise TraceabilityError(f"{ref} verification signoff drift")
        if item.get("bound_masterplan_git_blob_sha") != _git_blob_sha(
            root / "machine/ai_master_plan.json"
        ):
            raise TraceabilityError(f"{ref} bound masterplan digest stale")
        if item.get("bound_accountability_git_blob_sha") != _git_blob_sha(
            root / "machine/ai_build_accountability.json"
        ):
            raise TraceabilityError(f"{ref} bound accountability digest stale")


def _validate_behaviors(
    root: Path,
    requirements: set[str],
    behavior: dict[str, Any],
) -> set[str]:
    scenarios = behavior.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise TraceabilityError("behavior scenarios must be non-empty")
    by_ref: dict[str, list[dict[str, Any]]] = {}
    ids: set[str] = set()
    for item in scenarios:
        if not isinstance(item, dict):
            raise TraceabilityError("behavior scenario must be an object")
        scenario_id = item.get("id")
        if not isinstance(scenario_id, str) or scenario_id in ids:
            raise TraceabilityError(f"invalid/duplicate behavior id: {scenario_id!r}")
        ids.add(scenario_id)
        ref = item.get("volume_ref")
        by_ref.setdefault(ref, []).append(item)
        refs = item.get("requirement_refs")
        if not isinstance(refs, list) or not refs:
            raise TraceabilityError(f"{scenario_id} lacks requirement linkage")
        unknown = sorted(set(refs) - requirements)
        if unknown:
            raise TraceabilityError(
                f"{scenario_id} references unknown requirements: {unknown}"
            )
        test_ref = _repo_path(item.get("test_ref"))
        if not (root / test_ref).is_file():
            raise TraceabilityError(f"{scenario_id} test ref missing: {test_ref}")
        if not item.get("forbidden_outcomes"):
            raise TraceabilityError(f"{scenario_id} lacks forbidden outcomes")
    if set(by_ref) != set(TRACE_REFS):
        raise TraceabilityError("behavior scenarios must cover every P2 trace volume")
    return ids


def _validate_states(
    root: Path,
    schemas: dict[str, Any],
    catalogue: dict[str, Any],
) -> set[str]:
    if catalogue.get("source_schema_git_blob_sha") != _git_blob_sha(
        root / "machine/ai_runtime_schemas.json"
    ):
        raise TraceabilityError("state catalogue schema digest is stale")
    machines = catalogue.get("state_machines")
    if not isinstance(machines, list) or not machines:
        raise TraceabilityError("state machine catalogue must be non-empty")
    ids: set[str] = set()
    for item in machines:
        if not isinstance(item, dict):
            raise TraceabilityError("state machine entry must be an object")
        machine_id = item.get("id")
        if machine_id in ids:
            raise TraceabilityError(f"duplicate state machine: {machine_id}")
        ids.add(machine_id)
        enum_name = item.get("enum_name")
        if item.get("states") != schemas.get("enums", {}).get(enum_name):
            raise TraceabilityError(f"{machine_id} state set drift")
        terminals = item.get("terminal_states")
        if not isinstance(terminals, list) or not set(terminals) <= set(item["states"]):
            raise TraceabilityError(f"{machine_id} invalid terminal states")
        for field in ("transition_source", "transition_test_ref"):
            path = _repo_path(item.get(field))
            if not (root / path).is_file():
                raise TraceabilityError(f"{machine_id} {field} missing: {path}")
    return ids


def _validate_interfaces(
    root: Path,
    interfaces: dict[str, Any],
    standard: dict[str, Any],
) -> None:
    if standard.get("source_git_blob_sha") != _git_blob_sha(
        root / "machine/capability_interfaces.json"
    ):
        raise TraceabilityError("interface standard source digest is stale")
    rules = standard.get("rules")
    if not isinstance(rules, list) or not rules:
        raise TraceabilityError("interface lint rules must be non-empty")
    required: set[str] = set()
    required_nonempty: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("severity") != "blocking":
            raise TraceabilityError("interface lint rules must be blocking objects")
        required.update(rule.get("require", []))
        required_nonempty.update(rule.get("require_nonempty", []))
    entries = interfaces.get("entries")
    if not isinstance(entries, list) or not entries:
        raise TraceabilityError("capability interfaces must be non-empty")
    for entry in entries:
        edge_id = entry.get("id")
        for field in required:
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise TraceabilityError(f"{edge_id} missing interface field {field}")
        for field in required_nonempty:
            value = entry.get(field)
            if not isinstance(value, list) or not value:
                raise TraceabilityError(f"{edge_id} missing interface list {field}")


def _validate_schemas(
    root: Path,
    schemas: dict[str, Any],
    registry: dict[str, Any],
) -> set[str]:
    if registry.get("source_git_blob_sha") != _git_blob_sha(
        root / "machine/ai_runtime_schemas.json"
    ):
        raise TraceabilityError("schema registry source digest is stale")
    entries = registry.get("schemas")
    if not isinstance(entries, list):
        raise TraceabilityError("schema registry schemas must be a list")
    by_name = {item.get("name"): item for item in entries if isinstance(item, dict)}
    source_records = schemas.get("records", {})
    if set(by_name) != set(source_records) or len(by_name) != len(entries):
        raise TraceabilityError("schema registry coverage drift")
    ids: set[str] = set()
    for name, record in source_records.items():
        item = by_name[name]
        schema_id = f"SCHEMA-{name}"
        if item.get("id") != schema_id or schema_id in ids:
            raise TraceabilityError(f"{name} schema identity drift")
        ids.add(schema_id)
        if item.get("version") != record.get("schema_version"):
            raise TraceabilityError(f"{name} schema version drift")
        if item.get("owner_plane") != record.get("owner_plane"):
            raise TraceabilityError(f"{name} schema owner drift")
        if item.get("field_names") != sorted(record.get("fields", {})):
            raise TraceabilityError(f"{name} schema field inventory drift")
        if item.get("invariant_count") != len(record.get("invariants", [])):
            raise TraceabilityError(f"{name} schema invariant inventory drift")
    return ids


def _validate_compatibility(root: Path, model: dict[str, Any]) -> None:
    sources = model.get("sources")
    if not isinstance(sources, dict):
        raise TraceabilityError("compatibility model sources must be an object")
    for relative in sources.values():
        path = _repo_path(relative)
        if not (root / path).is_file():
            raise TraceabilityError(f"compatibility source missing: {path}")
    rules = model.get("change_rules")
    if not isinstance(rules, list) or not rules:
        raise TraceabilityError("compatibility change rules must be non-empty")
    changes = {rule.get("change"): rule for rule in rules if isinstance(rule, dict)}
    required = {
        "add_optional_response_field",
        "remove_field",
        "rename_field",
        "change_type_or_nullability",
        "add_closed_enum_value",
        "authority_semantics",
    }
    if set(changes) != required:
        raise TraceabilityError("compatibility rule set drift")
    for name in (
        "remove_field",
        "rename_field",
        "change_type_or_nullability",
        "authority_semantics",
    ):
        rule = changes[name]
        if rule.get("classification") != "incompatible":
            raise TraceabilityError(f"{name} must remain incompatible")
        requirements = set(rule.get("requires", []))
        if "rollback plan" not in requirements:
            raise TraceabilityError(f"{name} incompatible change lacks rollback plan")
    policy = model.get("policy", {})
    if policy.get("unknown_rule") != "Unclassified changes are incompatible by default.":
        raise TraceabilityError("compatibility model must fail closed on unknown changes")


def _validate_protocols(
    schemas: dict[str, Any],
    registry: dict[str, Any],
    protocols: dict[str, Any],
) -> set[str]:
    schema_names = {item.get("name") for item in registry.get("schemas", [])}
    source_records = schemas.get("records", {})
    entries = protocols.get("protocols")
    if not isinstance(entries, list) or not entries:
        raise TraceabilityError("internal protocol registry must be non-empty")
    ids: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise TraceabilityError("internal protocol entry must be an object")
        protocol_id = item.get("id")
        if not isinstance(protocol_id, str) or protocol_id in ids:
            raise TraceabilityError(f"invalid/duplicate protocol id: {protocol_id!r}")
        ids.add(protocol_id)
        envelope_names = item.get("envelope_schemas")
        if not isinstance(envelope_names, list) or not envelope_names:
            raise TraceabilityError(f"{protocol_id} lacks envelope schemas")
        unknown = sorted(set(envelope_names) - schema_names)
        if unknown:
            raise TraceabilityError(
                f"{protocol_id} references unregistered schemas: {unknown}"
            )
        field_union: set[str] = set()
        for name in envelope_names:
            field_union.update(source_records[name].get("fields", {}))
        for group in ("correlation_fields", "deadline_fields", "idempotency_fields"):
            values = item.get(group)
            if not isinstance(values, list):
                raise TraceabilityError(f"{protocol_id} {group} must be a list")
            missing = sorted(set(values) - field_union)
            if missing:
                raise TraceabilityError(
                    f"{protocol_id} {group} not represented by envelopes: {missing}"
                )
        if not isinstance(item.get("tracing"), str) or not item["tracing"].strip():
            raise TraceabilityError(f"{protocol_id} lacks tracing semantics")
    return ids


def _validate_graph(
    root: Path,
    graph: dict[str, Any],
    requirements: set[str],
    behavior_ids: set[str],
    capability_ids: set[str],
) -> dict[str, Any]:
    for source in graph.get("sources", []):
        path = _repo_path(source)
        if not (root / path).is_file():
            raise TraceabilityError(f"trace graph source missing: {path}")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise TraceabilityError("trace graph nodes/edges must be lists")
    by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            raise TraceabilityError("invalid trace node")
        node_id = node["id"]
        if node_id in by_id:
            raise TraceabilityError(f"duplicate trace node id: {node_id}")
        by_id[node_id] = node
        if node.get("type") in {"test", "validator", "authority"}:
            path = node.get("path")
            if isinstance(path, str) and not (root / _repo_path(path)).is_file():
                raise TraceabilityError(f"trace node path missing: {node_id} -> {path}")

    edge_ids: set[str] = set()
    outgoing: dict[str, list[dict[str, Any]]] = {}
    incoming: dict[str, list[dict[str, Any]]] = {}
    dangling = 0
    for edge in edges:
        if not isinstance(edge, dict) or not isinstance(edge.get("id"), str):
            raise TraceabilityError("invalid trace edge")
        edge_id = edge["id"]
        if edge_id in edge_ids:
            raise TraceabilityError(f"duplicate trace edge id: {edge_id}")
        edge_ids.add(edge_id)
        source = edge.get("from")
        target = edge.get("to")
        if source not in by_id or target not in by_id:
            dangling += 1
            continue
        outgoing.setdefault(source, []).append(edge)
        incoming.setdefault(target, []).append(edge)
    if dangling:
        raise TraceabilityError(f"trace graph has {dangling} dangling edges")

    req_nodes = {node_id for node_id, node in by_id.items() if node.get("type") == "requirement"}
    if req_nodes != requirements:
        raise TraceabilityError("trace graph requirement node coverage drift")
    graph_caps = {node_id for node_id, node in by_id.items() if node.get("type") == "capability"}
    if not graph_caps <= capability_ids:
        raise TraceabilityError("trace graph references unknown capability IDs")
    graph_behaviors = {node_id for node_id, node in by_id.items() if node.get("type") == "behavior"}
    if graph_behaviors != behavior_ids:
        raise TraceabilityError("trace graph behavior node coverage drift")

    for req_id in requirements:
        inc = incoming.get(req_id, [])
        out = outgoing.get(req_id, [])
        if not any(
            edge.get("kind") == "defines"
            and by_id[edge["from"]].get("type") == "volume"
            for edge in inc
        ):
            raise TraceabilityError(f"{req_id} lacks defining volume edge")
        if not any(edge.get("kind") == "requires_capability" for edge in out):
            raise TraceabilityError(f"{req_id} lacks capability trace")
        if not any(
            edge.get("kind") == "verified_by"
            and by_id[edge["to"]].get("type") == "test"
            for edge in out
        ):
            raise TraceabilityError(f"{req_id} lacks test trace")

    for behavior_id in behavior_ids:
        inc = incoming.get(behavior_id, [])
        out = outgoing.get(behavior_id, [])
        if not any(edge.get("kind") == "specified_by" for edge in inc):
            raise TraceabilityError(f"{behavior_id} lacks requirement trace")
        if not any(edge.get("kind") == "verified_by" for edge in out):
            raise TraceabilityError(f"{behavior_id} lacks test trace")

    volume_nodes = {
        node_id for node_id, node in by_id.items() if node.get("type") == "volume"
    }
    if volume_nodes != set(TRACE_REFS):
        raise TraceabilityError("trace graph volume coverage drift")
    for ref in TRACE_REFS:
        if not any(
            edge.get("kind") == "governed_by" for edge in outgoing.get(ref, [])
        ):
            raise TraceabilityError(f"{ref} lacks trace validator edge")
        if not any(
            edge.get("kind") == "implemented_by" for edge in outgoing.get(ref, [])
        ):
            raise TraceabilityError(f"{ref} lacks machine authority edge")

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "dangling_edge_count": dangling,
        "requirement_node_count": len(req_nodes),
        "volume_node_count": len(volume_nodes),
        "outgoing": outgoing,
        "incoming": incoming,
        "nodes": by_id,
    }


def _evaluate_nfrs(
    nfr: dict[str, Any],
    *,
    requirement_count: int,
    graph_stats: dict[str, Any],
    taxonomy: dict[str, Any],
    master: dict[str, Any],
    schema_registry: dict[str, Any],
    schemas: dict[str, Any],
    interfaces: dict[str, Any],
) -> dict[str, float]:
    metrics = {
        "requirement_trace_coverage": (
            graph_stats["requirement_node_count"] / requirement_count
            if requirement_count
            else 0.0
        ),
        "dangling_trace_edges": float(graph_stats["dangling_edge_count"]),
        "volume_taxonomy_coverage": (
            len(taxonomy.get("volume_map", [])) / len(master.get("volumes", []))
            if master.get("volumes")
            else 0.0
        ),
        "schema_registry_coverage": (
            len(schema_registry.get("schemas", []))
            / len(schemas.get("records", {}))
            if schemas.get("records")
            else 0.0
        ),
        "interface_failure_contract_coverage": (
            sum(
                isinstance(edge.get("target_failure_contract"), str)
                and bool(edge["target_failure_contract"].strip())
                for edge in interfaces.get("entries", [])
            )
            / len(interfaces.get("entries", []))
            if interfaces.get("entries")
            else 0.0
        ),
    }
    entries = nfr.get("nfrs")
    if not isinstance(entries, list) or not entries:
        raise TraceabilityError("NFR registry must be non-empty")
    ids: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise TraceabilityError("NFR entry must be an object")
        nfr_id = item.get("id")
        if not isinstance(nfr_id, str) or nfr_id in ids:
            raise TraceabilityError(f"invalid/duplicate NFR id: {nfr_id!r}")
        ids.add(nfr_id)
        metric = item.get("metric")
        if metric not in metrics:
            raise TraceabilityError(f"{nfr_id} references unknown metric {metric!r}")
        measurement = _repo_path(item.get("measurement"))
        if not (ROOT / measurement).is_file():
            raise TraceabilityError(f"{nfr_id} measurement harness missing")
        actual = metrics[metric]
        threshold = item.get("threshold")
        operator = item.get("operator")
        passed = (
            actual >= threshold
            if operator == ">="
            else actual == float(threshold)
            if operator == "=="
            else False
        )
        if not passed:
            raise TraceabilityError(
                f"{nfr_id} hard NFR failed: {metric}={actual}, "
                f"operator={operator}, threshold={threshold}"
            )
    if nfr.get("policy", {}).get("non_compensable") != (
        "Every NFR is hard-gated independently; averages cannot offset a failed NFR."
    ):
        raise TraceabilityError("NFR policy must remain non-compensable")
    return metrics


def _impact(
    graph: dict[str, Any],
    changed_paths: Iterable[str],
) -> dict[str, Any]:
    nodes = {node["id"]: node for node in graph.get("nodes", [])}
    incoming: dict[str, list[str]] = {}
    for edge in graph.get("edges", []):
        incoming.setdefault(edge["to"], []).append(edge["from"])

    authority_by_path = {
        node.get("path"): node_id
        for node_id, node in nodes.items()
        if node.get("type") == "authority" and isinstance(node.get("path"), str)
    }
    changed = sorted({_repo_path(path.strip()) for path in changed_paths if path.strip()})
    matched = {
        path: authority_by_path[path]
        for path in changed
        if path in authority_by_path
    }

    impacted_nodes: set[str] = set(matched.values())
    queue = list(impacted_nodes)
    while queue:
        current = queue.pop()
        for predecessor in incoming.get(current, []):
            if predecessor not in impacted_nodes:
                impacted_nodes.add(predecessor)
                queue.append(predecessor)

    impacted_volumes = sorted(
        node_id
        for node_id in impacted_nodes
        if nodes.get(node_id, {}).get("type") == "volume"
    )
    impacted_requirements = sorted(
        node_id
        for node_id in impacted_nodes
        if nodes.get(node_id, {}).get("type") == "requirement"
    )
    return {
        "changed_paths": changed,
        "matched_authorities": matched,
        "impacted_volumes": impacted_volumes,
        "impacted_requirements": impacted_requirements,
    }


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    master = _load(root, "machine/ai_master_plan.json")
    accountability = _load(root, "machine/ai_build_accountability.json")
    interfaces = _load(root, "machine/capability_interfaces.json")
    schemas = _load(root, "machine/ai_runtime_schemas.json")

    master_by_ref = {
        volume.get("key"): volume
        for volume in master.get("volumes", [])
        if isinstance(volume, dict) and isinstance(volume.get("key"), str)
    }
    missing_trace = sorted(set(TRACE_REFS) - set(master_by_ref))
    if missing_trace:
        raise TraceabilityError(f"masterplan missing P2 trace volumes: {missing_trace}")

    authorities = {
        relative: _load(root, relative)
        for relative in AUTHORITY_BINDINGS
    }
    for relative, payload in authorities.items():
        _assert_masterplan_binding(payload, master_by_ref, relative)

    requirements = _validate_requirements(
        root,
        master_by_ref,
        authorities["machine/requirement_registry.json"],
    )
    capability_map = _validate_taxonomy(
        root,
        master,
        authorities["machine/capability_taxonomy.json"],
    )
    _validate_runtime_capabilities(
        root,
        interfaces,
        authorities["machine/capability_registry.json"],
    )
    _validate_maturity(
        root,
        master_by_ref,
        accountability,
        authorities["machine/capability_maturity.json"],
    )
    behavior_ids = _validate_behaviors(
        root,
        requirements,
        authorities["machine/behavior_specifications.json"],
    )
    state_ids = _validate_states(
        root,
        schemas,
        authorities["machine/state_machine_catalogue.json"],
    )
    _validate_interfaces(
        root,
        interfaces,
        authorities["machine/interface_standard.json"],
    )
    schema_ids = _validate_schemas(
        root,
        schemas,
        authorities["machine/schema_registry.json"],
    )
    _validate_compatibility(
        root,
        authorities["machine/compatibility_model.json"],
    )
    protocol_ids = _validate_protocols(
        schemas,
        authorities["machine/schema_registry.json"],
        authorities["machine/internal_protocols.json"],
    )
    graph_stats = _validate_graph(
        root,
        authorities["machine/master_traceability.json"],
        requirements,
        behavior_ids,
        set(capability_map.values()),
    )
    metrics = _evaluate_nfrs(
        authorities["machine/nfr_registry.json"],
        requirement_count=len(requirements),
        graph_stats=graph_stats,
        taxonomy=authorities["machine/capability_taxonomy.json"],
        master=master,
        schema_registry=authorities["machine/schema_registry.json"],
        schemas=schemas,
        interfaces=interfaces,
    )

    return {
        "status": "valid",
        "trace_volume_count": len(TRACE_REFS),
        "requirement_count": len(requirements),
        "capability_count": len(capability_map),
        "behavior_count": len(behavior_ids),
        "state_machine_count": len(state_ids),
        "schema_count": len(schema_ids),
        "protocol_count": len(protocol_ids),
        "trace_node_count": graph_stats["node_count"],
        "trace_edge_count": graph_stats["edge_count"],
        "nfr_metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--changed-file-list",
        help="Optional newline-delimited repository paths for trace impact analysis.",
    )
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    try:
        result = validate(root)
        if args.changed_file_list:
            changed = Path(args.changed_file_list).read_text(
                encoding="utf-8"
            ).splitlines()
            graph = _load(root, "machine/master_traceability.json")
            result["impact"] = _impact(graph, changed)
    except (TraceabilityError, OSError) as exc:
        print(f"P2 traceability: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "P2 traceability: OK "
            f"({result['trace_volume_count']} volumes, "
            f"{result['requirement_count']} requirements, "
            f"{result['trace_node_count']} nodes, "
            f"{result['trace_edge_count']} edges)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
