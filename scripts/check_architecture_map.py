#!/usr/bin/env python3
"""Validate the canonical machine-readable architecture map.

The architecture map links repository ownership to the assembled runtime
contract. Validation is intentionally dependency-free and fail-closed so it can
run early in CI before application dependencies are installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE_PATH = Path("machine/architecture.json")
RUNTIME_MANIFEST_PATH = Path("skeleton/app/manifest.json")


def _load_json(path: Path) -> dict[str, Any]:
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


def _normalized_repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError("must be a non-empty repository-relative POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("must be normalized and repository-relative")
    if pure.as_posix() != value:
        raise ValueError("must use canonical POSIX spelling")
    return value


def _require_list(payload: dict[str, Any], key: str, errors: list[str]) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        errors.append(f"{key} must be a list")
        return []
    return value


def _collect_unique_ids(
    items: list[Any],
    label: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(items):
        item_label = f"{label}[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{item_label} must be an object")
            continue
        item_id = raw.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"{item_label}.id must be a non-empty string")
            continue
        if item_id in result:
            errors.append(f"duplicate {label} id: {item_id}")
            continue
        result[item_id] = raw
    return result


def _validate_source_contracts(
    architecture: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> None:
    sources = architecture.get("sources")
    if not isinstance(sources, dict) or not sources:
        errors.append("sources must be a non-empty object")
        return

    for key, raw_path in sorted(sources.items()):
        try:
            relative = _normalized_repo_path(raw_path)
        except ValueError as exc:
            errors.append(f"sources.{key}: {exc}")
            continue
        if not (repo_root / relative).exists():
            errors.append(f"sources.{key}: missing path {relative}")


def _validate_roots(
    architecture: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    roots = _collect_unique_ids(
        _require_list(architecture, "canonical_roots", errors),
        "canonical_roots",
        errors,
    )
    seen_paths: dict[str, str] = {}
    for root_id, root in roots.items():
        try:
            path = _normalized_repo_path(root.get("path"))
        except ValueError as exc:
            errors.append(f"canonical_roots.{root_id}.path: {exc}")
            continue
        prior = seen_paths.get(path)
        if prior is not None:
            errors.append(
                f"canonical root path {path} is owned by both {prior} and {root_id}"
            )
        else:
            seen_paths[path] = root_id
        if not (repo_root / path).exists():
            errors.append(f"canonical root {root_id} points to missing path {path}")
        for required in ("class", "owner", "change_lane"):
            if not isinstance(root.get(required), str) or not root[required]:
                errors.append(f"canonical_roots.{root_id}.{required} must be non-empty")
    return roots


def _validate_zones(
    architecture: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    zones = _collect_unique_ids(
        _require_list(architecture, "zones", errors),
        "zones",
        errors,
    )
    for zone_id, zone in zones.items():
        roots = zone.get("roots")
        if not isinstance(roots, list) or not roots:
            errors.append(f"zones.{zone_id}.roots must be a non-empty list")
        else:
            for index, root in enumerate(roots):
                try:
                    normalized = _normalized_repo_path(root)
                except ValueError as exc:
                    errors.append(f"zones.{zone_id}.roots[{index}]: {exc}")
                    continue
                if not (repo_root / normalized).exists():
                    errors.append(
                        f"zones.{zone_id}.roots[{index}] points to missing path {normalized}"
                    )
        may_depend_on = zone.get("may_depend_on")
        if not isinstance(may_depend_on, list):
            errors.append(f"zones.{zone_id}.may_depend_on must be a list")
            continue
        for dependency in may_depend_on:
            if dependency not in zones:
                errors.append(
                    f"zones.{zone_id} depends on unknown zone {dependency!r}"
                )
            if dependency == zone_id:
                errors.append(f"zones.{zone_id} must not depend on itself")
    return zones


def _validate_zone_dag(
    zones: dict[str, dict[str, Any]],
    errors: list[str],
) -> list[str]:
    """Return a deterministic dependency-first zone order or reject cycles."""
    indegree = {zone_id: 0 for zone_id in zones}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for zone_id, zone in zones.items():
        for dependency in zone.get("may_depend_on", []):
            if dependency not in zones:
                continue
            outgoing[dependency].append(zone_id)
            indegree[zone_id] += 1

    queue = deque(sorted(zone_id for zone_id, degree in indegree.items() if degree == 0))
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for follower in sorted(outgoing[current]):
            indegree[follower] -= 1
            if indegree[follower] == 0:
                queue.append(follower)

    if len(order) != len(zones):
        cyclic = sorted(zone_id for zone_id, degree in indegree.items() if degree > 0)
        errors.append(f"zone dependency graph contains a cycle: {', '.join(cyclic)}")
    return order


def _validate_runtime_nodes(
    architecture: dict[str, Any],
    zones: dict[str, dict[str, Any]],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    nodes = _collect_unique_ids(
        _require_list(architecture, "runtime_nodes", errors),
        "runtime_nodes",
        errors,
    )
    for node_id, node in nodes.items():
        if node.get("manifest_service") != node_id:
            errors.append(
                f"runtime_nodes.{node_id}.manifest_service must equal node id"
            )
        zone = node.get("zone")
        if zone not in zones:
            errors.append(f"runtime_nodes.{node_id} references unknown zone {zone!r}")
        try:
            _normalized_repo_path(node.get("path"))
        except ValueError as exc:
            errors.append(f"runtime_nodes.{node_id}.path: {exc}")
        dependencies = node.get("depends_on")
        if not isinstance(dependencies, list):
            errors.append(f"runtime_nodes.{node_id}.depends_on must be a list")
            continue
        if len(dependencies) != len(set(dependencies)):
            errors.append(f"runtime_nodes.{node_id}.depends_on contains duplicates")
        for dependency in dependencies:
            if dependency == node_id:
                errors.append(f"runtime node {node_id} must not depend on itself")
    for node_id, node in nodes.items():
        for dependency in node.get("depends_on", []):
            if dependency not in nodes:
                errors.append(
                    f"runtime node {node_id} depends on unknown node {dependency!r}"
                )
    return nodes


def _validate_runtime_dag(
    nodes: dict[str, dict[str, Any]],
    errors: list[str],
) -> list[str]:
    indegree = {node_id: 0 for node_id in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for node_id, node in nodes.items():
        for dependency in node.get("depends_on", []):
            if dependency not in nodes:
                continue
            outgoing[dependency].append(node_id)
            indegree[node_id] += 1

    queue = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for follower in sorted(outgoing[current]):
            indegree[follower] -= 1
            if indegree[follower] == 0:
                queue.append(follower)

    if len(order) != len(nodes):
        cyclic = sorted(node_id for node_id, degree in indegree.items() if degree > 0)
        errors.append(f"runtime dependency graph contains a cycle: {', '.join(cyclic)}")
    return order


def _validate_runtime_manifest_alignment(
    architecture: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    repo_root: Path,
    errors: list[str],
) -> None:
    sources = architecture.get("sources", {})
    runtime_path = sources.get("runtime_contract", RUNTIME_MANIFEST_PATH.as_posix())
    try:
        runtime_relative = _normalized_repo_path(runtime_path)
    except ValueError as exc:
        errors.append(f"runtime contract path: {exc}")
        return
    try:
        manifest = _load_json(repo_root / runtime_relative)
    except ValueError as exc:
        errors.append(str(exc))
        return

    link = manifest.get("architecture")
    if not isinstance(link, dict):
        errors.append(f"{runtime_relative}.architecture must be an object")
    else:
        expected_link = {
            "contract": ARCHITECTURE_PATH.as_posix(),
            "validator": architecture.get("sources", {}).get("validator"),
            "documentation": architecture.get("sources", {}).get("human_map"),
            "tag": architecture.get("architecture_tag"),
            "structure_tag": architecture.get("structural_blueprint", {}).get("structure_tag"),
        }
        for field, expected in expected_link.items():
            if link.get(field) != expected:
                errors.append(
                    f"{runtime_relative}.architecture.{field} drift: "
                    f"manifest={link.get(field)!r} expected={expected!r}"
                )

    raw_services = manifest.get("services")
    if not isinstance(raw_services, list):
        errors.append(f"{runtime_relative}.services must be a list")
        return
    services: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_services):
        if not isinstance(raw, dict):
            errors.append(f"{runtime_relative}.services[{index}] must be an object")
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{runtime_relative}.services[{index}].name must be non-empty")
            continue
        if name in services:
            errors.append(f"duplicate runtime manifest service: {name}")
            continue
        services[name] = raw

    if set(nodes) != set(services):
        missing = sorted(set(services) - set(nodes))
        extra = sorted(set(nodes) - set(services))
        if missing:
            errors.append(
                "architecture map is missing runtime manifest services: "
                + ", ".join(missing)
            )
        if extra:
            errors.append(
                "architecture map declares services absent from runtime manifest: "
                + ", ".join(extra)
            )

    fields = ("path", "kind", "canonical")
    for name in sorted(set(nodes) & set(services)):
        node = nodes[name]
        service = services[name]
        for field in fields:
            if node.get(field) != service.get(field):
                errors.append(
                    f"runtime service {name}.{field} drift: "
                    f"architecture={node.get(field)!r} manifest={service.get(field)!r}"
                )
        architecture_deps = node.get("depends_on", [])
        manifest_deps = service.get("depends_on", [])
        if architecture_deps != manifest_deps:
            errors.append(
                f"runtime service {name}.depends_on drift: "
                f"architecture={architecture_deps!r} manifest={manifest_deps!r}"
            )



def _validate_repository_manifest_alignment(
    architecture: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> None:
    sources = architecture.get("sources", {})
    repository_path = sources.get("repository_contract")
    try:
        repository_relative = _normalized_repo_path(repository_path)
        manifest = _load_json(repo_root / repository_relative)
    except ValueError as exc:
        errors.append(f"repository contract: {exc}")
        return

    assembly = manifest.get("assembly")
    if not isinstance(assembly, dict):
        errors.append(f"{repository_relative}.assembly must be an object")
        return

    structure_tag = architecture.get("structural_blueprint", {}).get("structure_tag")
    expected = {
        "architecture_contract": ARCHITECTURE_PATH.as_posix(),
        "structure_tag": structure_tag,
    }
    for field, value in expected.items():
        if assembly.get(field) != value:
            errors.append(
                f"{repository_relative}.assembly.{field} drift: "
                f"manifest={assembly.get(field)!r} expected={value!r}"
            )

    layers = assembly.get("layers")
    if not isinstance(layers, list):
        errors.append(f"{repository_relative}.assembly.layers must be a list")
        return
    architecture_layers = [
        layer
        for layer in layers
        if isinstance(layer, dict) and layer.get("name") == "architecture-map"
    ]
    if len(architecture_layers) != 1:
        errors.append(
            f"{repository_relative}.assembly.layers must contain exactly one architecture-map layer"
        )
        return
    layer = architecture_layers[0]
    if layer.get("tag") != architecture.get("architecture_tag"):
        errors.append(
            f"{repository_relative} architecture layer tag drift: "
            f"manifest={layer.get('tag')!r} expected={architecture.get('architecture_tag')!r}"
        )
    if layer.get("structure_tag") != structure_tag:
        errors.append(
            f"{repository_relative} architecture layer structure_tag drift: "
            f"manifest={layer.get('structure_tag')!r} expected={structure_tag!r}"
        )
    if layer.get("ref") != assembly.get("architecture_branch"):
        errors.append(
            f"{repository_relative} architecture layer ref must equal assembly.architecture_branch"
        )


def _validate_interfaces(
    architecture: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    roots: dict[str, dict[str, Any]],
    repo_root: Path,
    errors: list[str],
) -> None:
    interfaces = _collect_unique_ids(
        _require_list(architecture, "interfaces", errors),
        "interfaces",
        errors,
    )
    root_paths = {
        root.get("path")
        for root in roots.values()
        if isinstance(root.get("path"), str)
    }
    for interface_id, interface in interfaces.items():
        for endpoint_key in ("from", "to"):
            endpoint = interface.get(endpoint_key)
            if not isinstance(endpoint, str) or not endpoint:
                errors.append(
                    f"interfaces.{interface_id}.{endpoint_key} must be non-empty"
                )
                continue
            if endpoint in nodes or endpoint in roots or endpoint in root_paths:
                continue
            try:
                path = _normalized_repo_path(endpoint)
            except ValueError:
                errors.append(
                    f"interfaces.{interface_id}.{endpoint_key} references "
                    f"unknown node or path {endpoint!r}"
                )
                continue
            if not (repo_root / path).exists():
                errors.append(
                    f"interfaces.{interface_id}.{endpoint_key} references "
                    f"missing path {endpoint!r}"
                )
        for required in ("transport", "contract"):
            if not isinstance(interface.get(required), str) or not interface[required]:
                errors.append(f"interfaces.{interface_id}.{required} must be non-empty")


def _validate_change_routing(
    architecture: dict[str, Any],
    roots: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    routing = _require_list(architecture, "change_routing", errors)
    lanes: set[str] = set()
    for index, raw in enumerate(routing):
        label = f"change_routing[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{label} must be an object")
            continue
        lane = raw.get("lane")
        if not isinstance(lane, str) or not lane:
            errors.append(f"{label}.lane must be non-empty")
            continue
        if lane in lanes:
            errors.append(f"duplicate change-routing lane: {lane}")
        lanes.add(lane)
        paths = raw.get("paths")
        checks = raw.get("minimum_checks")
        if not isinstance(paths, list) or not paths:
            errors.append(f"{label}.paths must be a non-empty list")
        if not isinstance(checks, list) or not checks:
            errors.append(f"{label}.minimum_checks must be a non-empty list")

    root_lanes = {
        root.get("change_lane")
        for root in roots.values()
        if root.get("class") in {"runtime", "accelerator", "control"}
    }
    missing = sorted(lane for lane in root_lanes if lane not in lanes)
    if missing:
        errors.append(
            "canonical runtime/control roots lack change-routing lanes: "
            + ", ".join(missing)
        )


def _validate_top_level_policy(
    architecture: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> int:
    policy = architecture.get("top_level_policy")
    if not isinstance(policy, dict):
        errors.append("top_level_policy must be an object")
        return 0
    if policy.get("new_runtime_root") != "forbidden-unless-declared":
        errors.append(
            "top_level_policy.new_runtime_root must be 'forbidden-unless-declared'"
        )

    categories = (
        "runtime_roots",
        "control_roots",
        "evidence_roots",
        "transitional_roots",
        "legacy_root_entrypoints",
    )
    seen: dict[str, str] = {}
    count = 0
    for category in categories:
        values = policy.get(category)
        if not isinstance(values, list):
            errors.append(f"top_level_policy.{category} must be a list")
            continue
        for index, raw_path in enumerate(values):
            try:
                path = _normalized_repo_path(raw_path)
            except ValueError as exc:
                errors.append(f"top_level_policy.{category}[{index}]: {exc}")
                continue
            prior = seen.get(path)
            if prior is not None:
                errors.append(
                    f"top-level path {path} is declared in both {prior} and {category}"
                )
            else:
                seen[path] = category
            if not (repo_root / path).exists():
                errors.append(
                    f"top_level_policy.{category} references missing path {path}"
                )
            count += 1
    return count



def _path_is_within(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


def _validate_structural_blueprint(
    architecture: dict[str, Any],
    zones: dict[str, dict[str, Any]],
    repo_root: Path,
    errors: list[str],
) -> dict[str, int]:
    blueprint = architecture.get("structural_blueprint")
    if not isinstance(blueprint, dict):
        errors.append("structural_blueprint must be an object")
        return {}

    if blueprint.get("schema_version") != 1:
        errors.append("structural_blueprint.schema_version must be exactly 1")
    structure_tag = blueprint.get("structure_tag")
    if not isinstance(structure_tag, str) or not structure_tag.startswith("structure-map/"):
        errors.append("structural_blueprint.structure_tag must start with 'structure-map/'")

    levels = blueprint.get("levels")
    if not isinstance(levels, list):
        errors.append("structural_blueprint.levels must be a list")
        levels = []
    level_ids: list[str] = []
    for index, level in enumerate(levels):
        label = f"structural_blueprint.levels[{index}]"
        if not isinstance(level, dict):
            errors.append(f"{label} must be an object")
            continue
        level_id = level.get("id")
        if not isinstance(level_id, str) or not level_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if level_id in level_ids:
            errors.append(f"duplicate structural level: {level_id}")
        level_ids.append(level_id)
        for key in ("name", "unit", "rule"):
            if not isinstance(level.get(key), str) or not level[key].strip():
                errors.append(f"{label}.{key} must be non-empty")
    if level_ids != ["L0", "L1", "L2", "L3", "L4"]:
        errors.append("structural_blueprint.levels must declare L0 through L4 in order")

    required_rules = (
        "plane_owner_must_materialize",
        "plane_owner_must_be_inside_assigned_zone",
        "construction_plane_must_be_placed_exactly_once",
        "cross_zone_plane_dependency_must_follow_zone_dag",
        "transitional_root_may_not_own_plane",
        "composition_roots_may_wire_but_not_redefine_capability_ownership",
        "state_class_has_single_authority",
    )
    rules = blueprint.get("dependency_rules")
    if not isinstance(rules, dict):
        errors.append("structural_blueprint.dependency_rules must be an object")
        rules = {}
    for key in required_rules:
        if rules.get(key) is not True:
            errors.append(f"structural_blueprint.dependency_rules.{key} must be true")

    construction = architecture.get("construction")
    if not isinstance(construction, dict):
        errors.append("construction must be an object for structural blueprint validation")
        return {}
    try:
        contract_path = _normalized_repo_path(construction.get("contract"))
        contract = _load_json(repo_root / contract_path)
    except ValueError as exc:
        errors.append(f"structural blueprint construction contract: {exc}")
        return {}

    raw_planes = contract.get("planes")
    if not isinstance(raw_planes, list):
        errors.append("construction contract planes must be a list")
        raw_planes = []
    planes: dict[str, dict[str, Any]] = {}
    for index, plane in enumerate(raw_planes):
        if not isinstance(plane, dict):
            errors.append(f"construction planes[{index}] must be an object")
            continue
        plane_id = plane.get("id")
        if not isinstance(plane_id, str) or not plane_id:
            errors.append(f"construction planes[{index}].id must be non-empty")
            continue
        if plane_id in planes:
            errors.append(f"duplicate construction plane: {plane_id}")
            continue
        planes[plane_id] = plane

    policy = architecture.get("top_level_policy")
    transitional: list[str] = []
    if isinstance(policy, dict):
        values = policy.get("transitional_roots")
        if isinstance(values, list):
            for raw in values:
                try:
                    transitional.append(_normalized_repo_path(raw))
                except ValueError as exc:
                    errors.append(f"top_level_policy.transitional_roots: {exc}")

    placements_raw = blueprint.get("plane_placements")
    if not isinstance(placements_raw, list):
        errors.append("structural_blueprint.plane_placements must be a list")
        placements_raw = []
    placements: dict[str, dict[str, Any]] = {}
    for index, placement in enumerate(placements_raw):
        label = f"structural_blueprint.plane_placements[{index}]"
        if not isinstance(placement, dict):
            errors.append(f"{label} must be an object")
            continue
        plane_id = placement.get("plane")
        if not isinstance(plane_id, str) or not plane_id:
            errors.append(f"{label}.plane must be non-empty")
            continue
        if plane_id in placements:
            errors.append(f"duplicate plane placement: {plane_id}")
            continue
        placements[plane_id] = placement
        plane = planes.get(plane_id)
        if plane is None:
            errors.append(f"plane placement references unknown construction plane: {plane_id}")
            continue
        zone_id = placement.get("zone")
        if not isinstance(zone_id, str) or zone_id not in zones:
            errors.append(f"plane placement {plane_id} references unknown zone: {zone_id}")
            continue
        owner = placement.get("owner")
        try:
            owner_path = _normalized_repo_path(owner)
        except ValueError as exc:
            errors.append(f"plane placement {plane_id}.owner: {exc}")
            continue
        if owner_path != plane.get("owner"):
            errors.append(
                f"plane placement {plane_id} owner {owner_path} does not match "
                f"construction owner {plane.get('owner')}"
            )
        owner_abs = repo_root / owner_path
        if not owner_abs.exists():
            errors.append(f"plane placement {plane_id} owner is missing: {owner_path}")
        unit_type = placement.get("unit_type")
        if unit_type not in {"module", "package"}:
            errors.append(f"plane placement {plane_id}.unit_type must be module or package")
        elif unit_type == "module" and owner_abs.exists() and not owner_abs.is_file():
            errors.append(f"plane placement {plane_id} declares module but owner is not a file")
        elif unit_type == "package" and owner_abs.exists() and not owner_abs.is_dir():
            errors.append(f"plane placement {plane_id} declares package but owner is not a directory")

        zone_roots: list[str] = []
        for raw_root in zones[zone_id].get("roots", []):
            try:
                zone_roots.append(_normalized_repo_path(raw_root))
            except ValueError:
                continue
        if not any(_path_is_within(owner_path, root) for root in zone_roots):
            errors.append(
                f"plane placement {plane_id} owner {owner_path} is outside zone {zone_id}"
            )
        if any(_path_is_within(owner_path, root) for root in transitional):
            errors.append(
                f"plane placement {plane_id} illegally uses transitional owner {owner_path}"
            )
        for key in ("boundary_class", "exposure"):
            if not isinstance(placement.get(key), str) or not placement[key].strip():
                errors.append(f"plane placement {plane_id}.{key} must be non-empty")

    missing_placements = sorted(set(planes) - set(placements))
    extra_placements = sorted(set(placements) - set(planes))
    if missing_placements:
        errors.append(
            "construction planes missing structural placement: "
            + ", ".join(missing_placements)
        )
    if extra_placements:
        errors.append(
            "structural placements without construction planes: "
            + ", ".join(extra_placements)
        )

    exceptions_raw = blueprint.get("dependency_exceptions")
    if not isinstance(exceptions_raw, list):
        errors.append("structural_blueprint.dependency_exceptions must be a list")
        exceptions_raw = []
    exception_ids: set[str] = set()
    exception_edges: dict[tuple[str, str], str] = {}
    declared_exception_edges: set[tuple[str, str]] = set()
    for index, exception in enumerate(exceptions_raw):
        label = f"structural_blueprint.dependency_exceptions[{index}]"
        if not isinstance(exception, dict):
            errors.append(f"{label} must be an object")
            continue
        exception_id = exception.get("id")
        if not isinstance(exception_id, str) or not exception_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if exception_id in exception_ids:
            errors.append(f"duplicate dependency exception id: {exception_id}")
        exception_ids.add(exception_id)

        source_planes = exception.get("source_planes")
        dependency_plane = exception.get("dependency_plane")
        from_zone = exception.get("from_zone")
        to_zone = exception.get("to_zone")
        kind = exception.get("kind")
        if not isinstance(source_planes, list) or not source_planes:
            errors.append(f"dependency exception {exception_id}.source_planes must be non-empty")
            source_planes = []
        if dependency_plane not in planes:
            errors.append(
                f"dependency exception {exception_id} references unknown dependency plane: "
                f"{dependency_plane}"
            )
        if from_zone not in zones or to_zone not in zones:
            errors.append(
                f"dependency exception {exception_id} must reference known from/to zones"
            )
        if kind not in {"ownership-migration", "control-observation"}:
            errors.append(
                f"dependency exception {exception_id}.kind must be ownership-migration "
                "or control-observation"
            )
        for key in ("rationale", "removal_condition"):
            if not isinstance(exception.get(key), str) or not exception[key].strip():
                errors.append(f"dependency exception {exception_id}.{key} must be non-empty")
        if "target_owner" in exception:
            try:
                _normalized_repo_path(exception.get("target_owner"))
            except ValueError as exc:
                errors.append(f"dependency exception {exception_id}.target_owner: {exc}")

        for source_plane in source_planes:
            if source_plane not in planes:
                errors.append(
                    f"dependency exception {exception_id} references unknown source plane: "
                    f"{source_plane}"
                )
                continue
            edge = (source_plane, dependency_plane)
            prior = exception_edges.get(edge)
            if prior is not None:
                errors.append(
                    f"dependency edge {source_plane}->{dependency_plane} is excepted by "
                    f"both {prior} and {exception_id}"
                )
            else:
                exception_edges[edge] = exception_id
            source_placement = placements.get(source_plane)
            target_placement = placements.get(dependency_plane)
            if source_placement is not None and source_placement.get("zone") != from_zone:
                errors.append(
                    f"dependency exception {exception_id} from_zone drift for {source_plane}: "
                    f"{source_placement.get('zone')} != {from_zone}"
                )
            if target_placement is not None and target_placement.get("zone") != to_zone:
                errors.append(
                    f"dependency exception {exception_id} to_zone drift for {dependency_plane}: "
                    f"{target_placement.get('zone')} != {to_zone}"
                )
            dependencies = planes[source_plane].get("depends_on", [])
            if dependency_plane not in dependencies:
                errors.append(
                    f"dependency exception {exception_id} does not match an actual "
                    f"construction edge {source_plane}->{dependency_plane}"
                )

    for plane_id, plane in planes.items():
        source = placements.get(plane_id)
        if source is None:
            continue
        source_zone = source.get("zone")
        for dependency in plane.get("depends_on", []):
            target = placements.get(dependency)
            if target is None:
                continue
            target_zone = target.get("zone")
            if source_zone == target_zone:
                continue
            allowed = zones.get(source_zone, {}).get("may_depend_on", [])
            if target_zone not in allowed:
                edge = (plane_id, dependency)
                if edge in exception_edges:
                    declared_exception_edges.add(edge)
                    continue
                errors.append(
                    f"cross-zone plane dependency {plane_id}({source_zone}) -> "
                    f"{dependency}({target_zone}) is not allowed by zone DAG "
                    "and has no bounded dependency exception"
                )

    unused_exceptions = sorted(set(exception_edges) - declared_exception_edges)
    for source_plane, dependency_plane in unused_exceptions:
        errors.append(
            f"dependency exception {source_plane}->{dependency_plane} is unnecessary; "
            "the zone DAG already permits the edge or the edge is intra-zone"
        )

    roots_raw = blueprint.get("composition_roots")
    if not isinstance(roots_raw, list):
        errors.append("structural_blueprint.composition_roots must be a list")
        roots_raw = []
    composition_ids: set[str] = set()
    composition_paths: set[str] = set()
    for index, root in enumerate(roots_raw):
        label = f"structural_blueprint.composition_roots[{index}]"
        if not isinstance(root, dict):
            errors.append(f"{label} must be an object")
            continue
        root_id = root.get("id")
        if not isinstance(root_id, str) or not root_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if root_id in composition_ids:
            errors.append(f"duplicate composition root id: {root_id}")
        composition_ids.add(root_id)
        try:
            path = _normalized_repo_path(root.get("path"))
        except ValueError as exc:
            errors.append(f"{label}.path: {exc}")
            continue
        if path in composition_paths:
            errors.append(f"duplicate composition root path: {path}")
        composition_paths.add(path)
        if not (repo_root / path).is_file():
            errors.append(f"composition root {root_id} must be a materialized file: {path}")
        zone_id = root.get("zone")
        if not isinstance(zone_id, str) or zone_id not in zones:
            errors.append(f"composition root {root_id} references unknown zone: {zone_id}")
        else:
            zone_roots = [
                str(raw) for raw in zones[zone_id].get("roots", []) if isinstance(raw, str)
            ]
            if not any(_path_is_within(path, zr) for zr in zone_roots):
                errors.append(f"composition root {root_id} path {path} is outside zone {zone_id}")
        if not isinstance(root.get("responsibility"), str) or not root["responsibility"].strip():
            errors.append(f"composition root {root_id}.responsibility must be non-empty")

    authorities_raw = blueprint.get("state_authorities")
    if not isinstance(authorities_raw, list):
        errors.append("structural_blueprint.state_authorities must be a list")
        authorities_raw = []
    state_names: set[str] = set()
    for index, authority in enumerate(authorities_raw):
        label = f"structural_blueprint.state_authorities[{index}]"
        if not isinstance(authority, dict):
            errors.append(f"{label} must be an object")
            continue
        state = authority.get("state")
        plane_id = authority.get("plane")
        owner = authority.get("owner")
        if not isinstance(state, str) or not state:
            errors.append(f"{label}.state must be non-empty")
            continue
        if state in state_names:
            errors.append(f"duplicate state authority: {state}")
        state_names.add(state)
        if plane_id not in planes:
            errors.append(f"state authority {state} references unknown plane: {plane_id}")
            continue
        if owner != planes[plane_id].get("owner"):
            errors.append(
                f"state authority {state} owner {owner} does not match plane "
                f"{plane_id} owner {planes[plane_id].get('owner')}"
            )

    recovery_raw = blueprint.get("recovery_domains")
    if not isinstance(recovery_raw, list):
        errors.append("structural_blueprint.recovery_domains must be a list")
        recovery_raw = []
    recovery_ids: set[str] = set()
    recovered_planes: dict[str, str] = {}
    for index, domain in enumerate(recovery_raw):
        label = f"structural_blueprint.recovery_domains[{index}]"
        if not isinstance(domain, dict):
            errors.append(f"{label} must be an object")
            continue
        domain_id = domain.get("id")
        if not isinstance(domain_id, str) or not domain_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if domain_id in recovery_ids:
            errors.append(f"duplicate recovery domain: {domain_id}")
        recovery_ids.add(domain_id)
        domain_planes = domain.get("planes")
        if not isinstance(domain_planes, list) or not domain_planes:
            errors.append(f"recovery domain {domain_id}.planes must be non-empty")
            continue
        for plane_id in domain_planes:
            if plane_id not in planes:
                errors.append(
                    f"recovery domain {domain_id} references unknown plane: {plane_id}"
                )
                continue
            prior = recovered_planes.get(plane_id)
            if prior is not None:
                errors.append(
                    f"construction plane {plane_id} belongs to multiple recovery domains: "
                    f"{prior}, {domain_id}"
                )
            else:
                recovered_planes[plane_id] = domain_id
        for key in ("restart_scope", "degraded_mode"):
            if not isinstance(domain.get(key), str) or not domain[key].strip():
                errors.append(f"recovery domain {domain_id}.{key} must be non-empty")
    missing_recovery = sorted(set(planes) - set(recovered_planes))
    if missing_recovery:
        errors.append(
            "construction planes missing recovery domain: " + ", ".join(missing_recovery)
        )

    invariants = blueprint.get("invariants")
    if not isinstance(invariants, list) or not invariants or any(
        not isinstance(item, str) or not item.strip() for item in invariants
    ):
        errors.append("structural_blueprint.invariants must be a non-empty string list")

    return {
        "levels": len(level_ids),
        "plane_placements": len(placements),
        "composition_roots": len(composition_ids),
        "state_authorities": len(state_names),
        "recovery_domains": len(recovery_ids),
        "dependency_exceptions": len(exception_ids),
    }


def validate_architecture(repo_root: Path = REPO_ROOT) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    architecture_path = repo_root / ARCHITECTURE_PATH
    try:
        architecture = _load_json(architecture_path)
    except ValueError as exc:
        return [str(exc)], {}

    if architecture.get("schema_version") != 1:
        errors.append("schema_version must be exactly 1")
    if architecture.get("status") != "active":
        errors.append("status must be 'active'")
    if not isinstance(architecture.get("architecture_version"), str):
        errors.append("architecture_version must be a string")
    if not isinstance(architecture.get("architecture_tag"), str):
        errors.append("architecture_tag must be a string")

    _validate_source_contracts(architecture, repo_root, errors)
    roots = _validate_roots(architecture, repo_root, errors)
    zones = _validate_zones(architecture, repo_root, errors)
    zone_order = _validate_zone_dag(zones, errors)
    nodes = _validate_runtime_nodes(architecture, zones, errors)
    order = _validate_runtime_dag(nodes, errors)
    _validate_runtime_manifest_alignment(architecture, nodes, repo_root, errors)
    _validate_repository_manifest_alignment(architecture, repo_root, errors)
    _validate_interfaces(architecture, nodes, roots, repo_root, errors)
    _validate_change_routing(architecture, roots, errors)
    top_level_paths = _validate_top_level_policy(architecture, repo_root, errors)
    structure = _validate_structural_blueprint(architecture, zones, repo_root, errors)

    summary = {
        "ok": not errors,
        "architecture_version": architecture.get("architecture_version"),
        "architecture_tag": architecture.get("architecture_tag"),
        "canonical_roots": len(roots),
        "zones": len(zones),
        "zone_order": zone_order,
        "runtime_nodes": len(nodes),
        "runtime_order": order,
        "interfaces": len(architecture.get("interfaces", []))
        if isinstance(architecture.get("interfaces"), list)
        else 0,
        "top_level_paths": top_level_paths,
        "structure": structure,
        "errors": errors,
    }
    return errors, summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable validation summary",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors, summary = validate_architecture()

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif errors:
        print("architecture-map: rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
    else:
        zone_order = " -> ".join(summary["zone_order"])
        order = " -> ".join(summary["runtime_order"])
        print(
            "architecture-map: OK "
            f"(tag={summary['architecture_tag']}; "
            f"roots={summary['canonical_roots']}; "
            f"zones={summary['zones']}; "
            f"nodes={summary['runtime_nodes']}; "
            f"interfaces={summary['interfaces']}; "
            f"top-level={summary['top_level_paths']}; "
            f"placements={summary['structure'].get('plane_placements', 0)}; "
            f"recovery-domains={summary['structure'].get('recovery_domains', 0)}; "
            f"dependency-exceptions={summary['structure'].get('dependency_exceptions', 0)}; "
            f"zone-order={zone_order}; "
            f"runtime-order={order})"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
