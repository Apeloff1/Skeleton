#!/usr/bin/env python3
"""Independent VOL-002 architecture-fitness and ownership verifier.

This verifier intentionally does not import scripts.check_architecture_map or
any runtime architecture owner. It re-derives a bounded set of closure
invariants directly from machine contracts and repository state, then emits an
exact-head evidence receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = Path("machine/architecture.json")
RUNTIME_MANIFEST = Path("skeleton/app/manifest.json")
MASTERPLAN = Path("machine/ai_master_plan.json")

REQUIRED_VOL002_PATHS = {
    "machine/architecture.json",
    "docs/ARCHITECTURE_MAP.md",
    "scripts/check_architecture_map.py",
    ".github/workflows/vol002-architecture-fitness.yml",
}
REQUIRED_VOL002_TESTS = {
    "skeleton/testing/test_architecture_map.py",
    "tests/test_architecture_boundaries.py",
    "tests/test_vol002_architecture_independent_verifier.py",
}
REQUIRED_VOL002_EVALUATIONS = {
    ".github/workflows/vol002-architecture-fitness.yml",
    "scripts/check_architecture_map.py --json",
    "scripts/verify_vol002_architecture_fitness.py",
}
REQUIRED_REQUIREMENT_PHRASES = (
    "one canonical architecture graph",
    "Reject illegal dependencies",
    "explicit gaps",
)


class VerificationError(RuntimeError):
    """The independent architecture verifier could not read its authority."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read JSON authority {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain a JSON object")
    return value


def _norm(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError("path must be non-empty normalized POSIX text")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("path must be repository-relative and normalized")
    if path.as_posix() != value:
        raise ValueError("path must use canonical POSIX spelling")
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


def _object_rows(
    payload: dict[str, Any],
    field: str,
    errors: list[str],
) -> list[dict[str, Any]]:
    raw = payload.get(field)
    if not isinstance(raw, list):
        errors.append(f"{field} must be a list")
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"{field}[{index}] must be an object")
            continue
        rows.append(item)
    return rows


def _unique_by_id(
    rows: Iterable[dict[str, Any]],
    label: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = row.get("id")
        if not isinstance(value, str) or not value:
            errors.append(f"{label} row has invalid id")
            continue
        if value in result:
            errors.append(f"duplicate {label} id: {value}")
            continue
        result[value] = row
    return result


def _verify_sources(
    architecture: dict[str, Any],
    root: Path,
    errors: list[str],
) -> dict[str, str]:
    raw = architecture.get("sources")
    if not isinstance(raw, dict) or not raw:
        errors.append("architecture sources must be a non-empty object")
        return {}
    digests: dict[str, str] = {}
    for key, value in sorted(raw.items()):
        try:
            relative = _norm(value)
        except ValueError as exc:
            errors.append(f"sources.{key}: {exc}")
            continue
        path = root / relative
        if not path.exists():
            errors.append(f"sources.{key} points to missing path: {relative}")
            continue
        if path.is_file():
            try:
                digests[key] = _digest_bytes(path.read_bytes())
            except OSError as exc:
                errors.append(f"cannot digest source {relative}: {type(exc).__name__}")
    return digests


def _verify_roots(
    architecture: dict[str, Any],
    root: Path,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    rows = _object_rows(architecture, "canonical_roots", errors)
    roots = _unique_by_id(rows, "canonical root", errors)
    owned_paths: dict[str, str] = {}
    for root_id, row in roots.items():
        try:
            relative = _norm(row.get("path"))
        except ValueError as exc:
            errors.append(f"canonical root {root_id}: {exc}")
            continue
        prior = owned_paths.get(relative)
        if prior is not None:
            errors.append(
                f"canonical root path {relative} is multiply owned by {prior} and {root_id}"
            )
        else:
            owned_paths[relative] = root_id
        if not (root / relative).exists():
            errors.append(f"canonical root {root_id} is not materialized: {relative}")
        for field in ("class", "owner", "change_lane"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                errors.append(f"canonical root {root_id} has invalid {field}")
    policy = architecture.get("top_level_policy")
    if not isinstance(policy, dict):
        errors.append("top_level_policy must be an object")
    else:
        runtime_roots = policy.get("runtime_roots")
        if not isinstance(runtime_roots, list):
            errors.append("top_level_policy.runtime_roots must be a list")
        else:
            known_paths = set(owned_paths)
            for relative in runtime_roots:
                if relative not in known_paths:
                    errors.append(
                        f"runtime root lacks canonical ownership: {relative!r}"
                    )
    return roots


def _acyclic(
    ids: set[str],
    dependencies: dict[str, list[str]],
    label: str,
    errors: list[str],
) -> list[str]:
    indegree = {item: 0 for item in ids}
    outgoing = {item: [] for item in ids}
    for item in sorted(ids):
        for dependency in dependencies.get(item, []):
            if dependency not in ids:
                errors.append(f"{label} {item} depends on unknown {dependency!r}")
                continue
            if dependency == item:
                errors.append(f"{label} {item} depends on itself")
                continue
            indegree[item] += 1
            outgoing[dependency].append(item)
    queue = sorted(item for item, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while queue:
        current = queue.pop(0)
        order.append(current)
        for follower in sorted(outgoing[current]):
            indegree[follower] -= 1
            if indegree[follower] == 0:
                queue.append(follower)
                queue.sort()
    if len(order) != len(ids):
        cyclic = sorted(item for item, degree in indegree.items() if degree > 0)
        errors.append(f"{label} dependency graph contains cycle: {', '.join(cyclic)}")
    return order


def _verify_zones(
    architecture: dict[str, Any],
    root: Path,
    errors: list[str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    rows = _object_rows(architecture, "zones", errors)
    zones = _unique_by_id(rows, "zone", errors)
    dependencies: dict[str, list[str]] = {}
    for zone_id, row in zones.items():
        roots = row.get("roots")
        if not isinstance(roots, list) or not roots:
            errors.append(f"zone {zone_id} roots must be non-empty")
        else:
            for value in roots:
                try:
                    relative = _norm(value)
                except ValueError as exc:
                    errors.append(f"zone {zone_id} root: {exc}")
                    continue
                if not (root / relative).exists():
                    errors.append(
                        f"zone {zone_id} points to missing root: {relative}"
                    )
        raw_dependencies = row.get("may_depend_on")
        if not isinstance(raw_dependencies, list):
            errors.append(f"zone {zone_id}.may_depend_on must be a list")
            dependencies[zone_id] = []
        else:
            dependencies[zone_id] = [str(value) for value in raw_dependencies]
    order = _acyclic(set(zones), dependencies, "zone", errors)
    return zones, order


def _verify_runtime(
    architecture: dict[str, Any],
    manifest: dict[str, Any],
    zones: dict[str, dict[str, Any]],
    root: Path,
    errors: list[str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    rows = _object_rows(architecture, "runtime_nodes", errors)
    nodes = _unique_by_id(rows, "runtime node", errors)
    dependencies: dict[str, list[str]] = {}
    for node_id, row in nodes.items():
        if row.get("manifest_service") != node_id:
            errors.append(f"runtime node {node_id} manifest_service mismatch")
        if row.get("zone") not in zones:
            errors.append(f"runtime node {node_id} has unknown zone")
        try:
            relative = _norm(row.get("path"))
        except ValueError as exc:
            errors.append(f"runtime node {node_id} path: {exc}")
        else:
            if not (root / relative).exists():
                errors.append(f"runtime node {node_id} path missing: {relative}")
        raw_dependencies = row.get("depends_on")
        if not isinstance(raw_dependencies, list):
            errors.append(f"runtime node {node_id}.depends_on must be a list")
            dependencies[node_id] = []
        else:
            dependencies[node_id] = [str(value) for value in raw_dependencies]

    services_raw = manifest.get("services")
    services: dict[str, dict[str, Any]] = {}
    if not isinstance(services_raw, list):
        errors.append("runtime manifest services must be a list")
    else:
        for row in services_raw:
            if not isinstance(row, dict):
                errors.append("runtime manifest service must be an object")
                continue
            name = row.get("name")
            if not isinstance(name, str) or not name:
                errors.append("runtime manifest service has invalid name")
                continue
            if name in services:
                errors.append(f"duplicate runtime manifest service: {name}")
                continue
            services[name] = row

    if set(nodes) != set(services):
        errors.append(
            "architecture/runtime manifest service identity drift: "
            f"architecture={sorted(nodes)} manifest={sorted(services)}"
        )
    for name in sorted(set(nodes) & set(services)):
        node = nodes[name]
        service = services[name]
        for field in ("path", "kind", "canonical", "depends_on"):
            if node.get(field) != service.get(field):
                errors.append(f"runtime service {name}.{field} drift")
    order = _acyclic(set(nodes), dependencies, "runtime node", errors)
    return nodes, order


def _find_volume(master: dict[str, Any], key: str) -> dict[str, Any] | None:
    rows = master.get("volumes")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("key") == key:
            return row
    return None


def _verify_masterplan(
    master: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    volume = _find_volume(master, "VOL-002")
    if volume is None:
        errors.append("masterplan is missing VOL-002")
        return {}
    if volume.get("title") != "System Architecture":
        errors.append("VOL-002 title drifted from canonical authority")
    if volume.get("scope") != "canonical-plan":
        errors.append("VOL-002 scope must remain canonical-plan")
    if volume.get("implementation_status") not in {"implemented", "hardened", "verified"}:
        errors.append("VOL-002 implementation status is below implemented")

    paths = set(volume.get("implementation_paths") or [])
    tests = set(volume.get("tests") or [])
    evaluations = set(volume.get("evaluations") or [])
    for label, required, actual in (
        ("implementation path", REQUIRED_VOL002_PATHS, paths),
        ("test", REQUIRED_VOL002_TESTS, tests),
        ("evaluation", REQUIRED_VOL002_EVALUATIONS, evaluations),
    ):
        missing = sorted(required - actual)
        if missing:
            errors.append(f"VOL-002 {label} binding incomplete: {', '.join(missing)}")

    requirements = tuple(str(value) for value in volume.get("requirements") or [])
    for phrase in REQUIRED_REQUIREMENT_PHRASES:
        if not any(phrase in requirement for requirement in requirements):
            errors.append(f"VOL-002 lost requirement invariant: {phrase}")

    binding = {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "completion_checkbox_mark": volume.get("completion_checkbox_mark"),
        "enterprise_grade_state": volume.get("enterprise_grade_state"),
        "enterprise_grade_target": volume.get("enterprise_grade_target"),
        "implementation_paths": sorted(paths),
        "tests": sorted(tests),
        "evaluations": sorted(evaluations),
        "gaps": list(volume.get("gaps") or []),
    }
    binding["binding_digest"] = _digest_json(binding)
    return binding


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    architecture = _load_json(root / ARCHITECTURE)
    manifest = _load_json(root / RUNTIME_MANIFEST)
    master = _load_json(root / MASTERPLAN)

    source_digests = _verify_sources(architecture, root, errors)
    roots = _verify_roots(architecture, root, errors)
    zones, zone_order = _verify_zones(architecture, root, errors)
    nodes, runtime_order = _verify_runtime(
        architecture,
        manifest,
        zones,
        root,
        errors,
    )
    volume = _verify_masterplan(master, errors)

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol002-architecture-v1",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "volume": "VOL-002",
        "architecture_digest": _digest_bytes((root / ARCHITECTURE).read_bytes()),
        "runtime_manifest_digest": _digest_bytes(
            (root / RUNTIME_MANIFEST).read_bytes()
        ),
        "source_digests": source_digests,
        "canonical_root_ids": sorted(roots),
        "zone_order": zone_order,
        "runtime_order": runtime_order,
        "runtime_node_ids": sorted(nodes),
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
    except (VerificationError, OSError) as exc:
        receipt = {
            "schema_version": 1,
            "verifier": "independent-vol002-architecture-v1",
            "head_sha": (
                os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
                or os.environ.get("GITHUB_SHA", "").strip()
                or "unknown"
            ),
            "volume": "VOL-002",
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
            "VOL-002 independent architecture fitness: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-002 independent architecture fitness: FAIL")
        for error in receipt["errors"]:
            print(f" - {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
