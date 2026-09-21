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
                    _normalized_repo_path(root)
                except ValueError as exc:
                    errors.append(f"zones.{zone_id}.roots[{index}]: {exc}")
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
    zones = _validate_zones(architecture, errors)
    nodes = _validate_runtime_nodes(architecture, zones, errors)
    order = _validate_runtime_dag(nodes, errors)
    _validate_runtime_manifest_alignment(architecture, nodes, repo_root, errors)
    _validate_interfaces(architecture, nodes, roots, repo_root, errors)
    _validate_change_routing(architecture, roots, errors)
    top_level_paths = _validate_top_level_policy(architecture, repo_root, errors)

    summary = {
        "ok": not errors,
        "architecture_version": architecture.get("architecture_version"),
        "architecture_tag": architecture.get("architecture_tag"),
        "canonical_roots": len(roots),
        "zones": len(zones),
        "runtime_nodes": len(nodes),
        "runtime_order": order,
        "interfaces": len(architecture.get("interfaces", []))
        if isinstance(architecture.get("interfaces"), list)
        else 0,
        "top_level_paths": top_level_paths,
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
        order = " -> ".join(summary["runtime_order"])
        print(
            "architecture-map: OK "
            f"(tag={summary['architecture_tag']}; "
            f"roots={summary['canonical_roots']}; "
            f"zones={summary['zones']}; "
            f"nodes={summary['runtime_nodes']}; "
            f"interfaces={summary['interfaces']}; "
            f"top-level={summary['top_level_paths']}; "
            f"runtime-order={order})"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
