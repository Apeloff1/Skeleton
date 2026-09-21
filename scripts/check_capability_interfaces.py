#!/usr/bin/env python3
"""Validate the complete construction-plane capability interface registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path("machine/capability_interfaces.json")
CONSTRUCTION_PATH = Path("machine/ai_app_construction.json")
ARCHITECTURE_PATH = Path("machine/architecture.json")

_ALLOWED_RELATIONS = frozenset({"runtime_dependency", "acceptance_target"})
_ALLOWED_STATUS = frozenset({"present", "partial"})


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"missing JSON contract: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {path}: line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from None
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError("must be a non-empty repository-relative POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("must be normalized and repository-relative")
    if pure.as_posix() != value:
        raise ValueError("must use canonical POSIX spelling")
    return value


def _strings(
    value: object,
    *,
    label: str,
    errors: list[str],
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return []
    if not value and not allow_empty:
        errors.append(f"{label} must not be empty")
    out: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be a non-empty string")
            continue
        out.append(item)
    if len(out) != len(set(out)):
        errors.append(f"{label} contains duplicates")
    return out


def _expected_edges(
    construction: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], set[tuple[str, str, str]]]:
    raw = construction.get("planes")
    if not isinstance(raw, list):
        raise ValueError("construction planes must be a list")

    planes: dict[str, dict[str, Any]] = {}
    for index, plane in enumerate(raw):
        if not isinstance(plane, dict):
            raise ValueError(f"construction planes[{index}] must be an object")
        plane_id = plane.get("id")
        if not isinstance(plane_id, str) or not plane_id:
            raise ValueError(f"construction planes[{index}].id must be non-empty")
        if plane_id in planes:
            raise ValueError(f"duplicate construction plane: {plane_id}")
        planes[plane_id] = plane

    edges: set[tuple[str, str, str]] = set()
    for plane_id, plane in planes.items():
        for relation, field in (
            ("runtime_dependency", "depends_on"),
            ("acceptance_target", "validates"),
        ):
            values = plane.get(field, [])
            if not isinstance(values, list):
                raise ValueError(f"construction plane {plane_id}.{field} must be a list")
            for target in values:
                if target not in planes:
                    raise ValueError(
                        f"construction plane {plane_id}.{field} references unknown plane {target!r}"
                    )
                edge = (relation, plane_id, target)
                if edge in edges:
                    raise ValueError(f"duplicate construction edge: {edge}")
                edges.add(edge)
    return planes, edges


def _placements(
    architecture: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    blueprint = architecture.get("structural_blueprint")
    if not isinstance(blueprint, dict):
        raise ValueError("architecture structural_blueprint must be an object")
    raw = blueprint.get("plane_placements")
    if not isinstance(raw, list):
        raise ValueError("structural_blueprint.plane_placements must be a list")
    result: dict[str, dict[str, Any]] = {}
    for index, placement in enumerate(raw):
        if not isinstance(placement, dict):
            raise ValueError(f"plane_placements[{index}] must be an object")
        plane = placement.get("plane")
        if not isinstance(plane, str) or not plane:
            raise ValueError(f"plane_placements[{index}].plane must be non-empty")
        if plane in result:
            raise ValueError(f"duplicate plane placement: {plane}")
        result[plane] = placement
    return result


def validate_interfaces(
    repo_root: Path = ROOT,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    try:
        registry = _load(repo_root / REGISTRY_PATH)
        construction = _load(repo_root / CONSTRUCTION_PATH)
        architecture = _load(repo_root / ARCHITECTURE_PATH)
        planes, expected_edges = _expected_edges(construction)
        placements = _placements(architecture)
    except ValueError as exc:
        return [str(exc)], {}

    if registry.get("schema_version") != 1:
        errors.append("interface registry schema_version must be exactly 1")
    if registry.get("status") != "active":
        errors.append("interface registry status must be active")
    if not isinstance(registry.get("registry_version"), str) or not registry["registry_version"]:
        errors.append("interface registry version must be a non-empty string")

    if registry.get("architecture_tag") != architecture.get("architecture_tag"):
        errors.append(
            "interface registry architecture_tag must match machine/architecture.json"
        )
    if registry.get("construction_version") != construction.get("construction_version"):
        errors.append(
            "interface registry construction_version must match AI construction contract"
        )

    source_contracts = registry.get("sources")
    if not isinstance(source_contracts, dict):
        errors.append("interface registry sources must be an object")
    else:
        expected_sources = {
            "architecture": ARCHITECTURE_PATH.as_posix(),
            "construction": CONSTRUCTION_PATH.as_posix(),
            "manual": "docs/AI_APP_CONSTRUCTION_MANUAL.md",
        }
        for key, expected in expected_sources.items():
            if source_contracts.get(key) != expected:
                errors.append(
                    f"interface registry source drift: {key}={source_contracts.get(key)!r} "
                    f"expected={expected!r}"
                )
            if not (repo_root / expected).exists():
                errors.append(f"interface registry source path missing: {expected}")

    zones_raw = architecture.get("zones")
    zones: dict[str, dict[str, Any]] = {}
    if not isinstance(zones_raw, list):
        errors.append("architecture zones must be a list")
    else:
        for zone in zones_raw:
            if isinstance(zone, dict) and isinstance(zone.get("id"), str):
                zones[zone["id"]] = zone

    raw_entries = registry.get("entries")
    if not isinstance(raw_entries, list):
        errors.append("interface registry entries must be a list")
        raw_entries = []

    ids: set[str] = set()
    observed_edges: set[tuple[str, str, str]] = set()
    relation_counts = {relation: 0 for relation in _ALLOWED_RELATIONS}
    boundary_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}

    for index, entry in enumerate(raw_entries):
        label = f"entries[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue

        edge_id = entry.get("id")
        relation = entry.get("relation")
        source = entry.get("source_plane")
        target = entry.get("target_plane")

        if not isinstance(edge_id, str) or not edge_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if edge_id in ids:
            errors.append(f"duplicate interface edge id: {edge_id}")
        ids.add(edge_id)

        if relation not in _ALLOWED_RELATIONS:
            errors.append(f"{label}.relation must be one of {sorted(_ALLOWED_RELATIONS)}")
            continue
        relation_counts[relation] += 1

        if source not in planes:
            errors.append(f"{label}.source_plane references unknown plane {source!r}")
            continue
        if target not in planes:
            errors.append(f"{label}.target_plane references unknown plane {target!r}")
            continue

        expected_id = f"{relation}:{source}->{target}"
        if edge_id != expected_id:
            errors.append(
                f"{label}.id drift: {edge_id!r} expected {expected_id!r}"
            )

        edge = (relation, source, target)
        if edge in observed_edges:
            errors.append(f"duplicate interface edge: {edge}")
        observed_edges.add(edge)

        source_plane = planes[source]
        target_plane = planes[target]
        source_placement = placements.get(source)
        target_placement = placements.get(target)
        if source_placement is None or target_placement is None:
            errors.append(
                f"{label} references plane without structural placement: {source}->{target}"
            )
            continue

        expected_values = {
            "source_owner": source_plane.get("owner"),
            "target_owner": target_plane.get("owner"),
            "source_zone": source_placement.get("zone"),
            "target_zone": target_placement.get("zone"),
            "target_failure_contract": target_plane.get("failure_mode"),
        }
        for key, expected in expected_values.items():
            if entry.get(key) != expected:
                errors.append(
                    f"{label}.{key} drift: {entry.get(key)!r} expected {expected!r}"
                )

        for key in ("source_owner", "target_owner"):
            try:
                relative = _repo_path(entry.get(key))
            except ValueError as exc:
                errors.append(f"{label}.{key}: {exc}")
                continue
            if not (repo_root / relative).exists():
                errors.append(f"{label}.{key} path missing: {relative}")

        source_zone = source_placement.get("zone")
        target_zone = target_placement.get("zone")
        expected_boundary = (
            "evidence-only"
            if relation == "acceptance_target"
            else ("intra-zone" if source_zone == target_zone else "cross-zone")
        )
        if entry.get("boundary") != expected_boundary:
            errors.append(
                f"{label}.boundary drift: {entry.get('boundary')!r} "
                f"expected {expected_boundary!r}"
            )

        expected_binding = (
            "evidence-contract"
            if relation == "acceptance_target"
            else "logical-contract"
        )
        if entry.get("binding") != expected_binding:
            errors.append(
                f"{label}.binding drift: {entry.get('binding')!r} "
                f"expected {expected_binding!r}"
            )

        boundary_counts[expected_boundary] = boundary_counts.get(expected_boundary, 0) + 1

        if relation == "runtime_dependency" and source_zone != target_zone:
            allowed = zones.get(str(source_zone), {}).get("may_depend_on", [])
            if target_zone not in allowed:
                errors.append(
                    f"cross-zone interface violates zone DAG: "
                    f"{source}({source_zone})->{target}({target_zone})"
                )

        surface = _strings(
            entry.get("target_contract_surface"),
            label=f"{label}.target_contract_surface",
            errors=errors,
        )
        expected_surface = target_plane.get("required_interfaces")
        if isinstance(expected_surface, list) and surface != expected_surface:
            errors.append(
                f"{label}.target_contract_surface drift from target plane"
            )

        _strings(
            entry.get("source_acceptance"),
            label=f"{label}.source_acceptance",
            errors=errors,
        )
        target_acceptance = _strings(
            entry.get("target_acceptance"),
            label=f"{label}.target_acceptance",
            errors=errors,
        )
        expected_target_acceptance = target_plane.get("acceptance")
        if (
            isinstance(expected_target_acceptance, list)
            and target_acceptance != expected_target_acceptance
        ):
            errors.append(f"{label}.target_acceptance drift from target plane")

        ownership_rule = entry.get("ownership_rule")
        if (
            not isinstance(ownership_rule, str)
            or "never transfers ownership" not in ownership_rule
        ):
            errors.append(
                f"{label}.ownership_rule must preserve target authority"
            )

        expected_status = (
            "partial"
            if source_plane.get("state") == "partial"
            or target_plane.get("state") == "partial"
            else "present"
        )
        status = entry.get("status")
        if status not in _ALLOWED_STATUS:
            errors.append(f"{label}.status must be one of {sorted(_ALLOWED_STATUS)}")
        elif status != expected_status:
            errors.append(
                f"{label}.status drift: {status!r} expected {expected_status!r}"
            )
        status_counts[expected_status] = status_counts.get(expected_status, 0) + 1

    missing = sorted(expected_edges - observed_edges)
    extra = sorted(observed_edges - expected_edges)
    for relation, source, target in missing:
        errors.append(
            f"construction edge missing interface entry: {relation}:{source}->{target}"
        )
    for relation, source, target in extra:
        errors.append(
            f"interface entry has no construction edge: {relation}:{source}->{target}"
        )

    invariants = _strings(
        registry.get("invariants"),
        label="interface registry invariants",
        errors=errors,
    )

    summary = {
        "ok": not errors,
        "architecture_tag": registry.get("architecture_tag"),
        "construction_version": registry.get("construction_version"),
        "registry_version": registry.get("registry_version"),
        "entries": len(raw_entries),
        "expected_edges": len(expected_edges),
        "relations": dict(sorted(relation_counts.items())),
        "boundaries": dict(sorted(boundary_counts.items())),
        "statuses": dict(sorted(status_counts.items())),
        "invariants": len(invariants),
        "errors": errors,
    }
    return errors, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    errors, summary = validate_interfaces()
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif errors:
        print("capability-interfaces: rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
    else:
        print(
            "capability-interfaces: OK "
            f"(tag={summary['architecture_tag']}; "
            f"version={summary['registry_version']}; "
            f"entries={summary['entries']}; "
            f"runtime={summary['relations'].get('runtime_dependency', 0)}; "
            f"acceptance={summary['relations'].get('acceptance_target', 0)}; "
            f"cross-zone={summary['boundaries'].get('cross-zone', 0)}; "
            f"partial={summary['statuses'].get('partial', 0)})"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
