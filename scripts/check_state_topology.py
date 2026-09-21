#!/usr/bin/env python3
"""Fail-closed validator for state authority, persistence, and recovery topology."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_PATH = Path("machine/state_topology.json")
ARCHITECTURE_PATH = Path("machine/architecture.json")
CONSTRUCTION_PATH = Path("machine/ai_app_construction.json")

_AUTHORITIES = frozenset(
    {
        "authoritative",
        "authoritative-unbound",
        "conditional-authoritative",
        "derived",
        "scratch",
        "mixed-transitional",
        "recovery-aid",
    }
)
_SOURCE_OF_TRUTH_AUTHORITIES = frozenset(
    {"authoritative", "authoritative-unbound", "conditional-authoritative"}
)
_NON_AUTHORITY_CLASSES = frozenset(
    {"derived", "scratch", "mixed-transitional", "recovery-aid"}
)


def _load(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"missing state-topology source: {path}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {path}: line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _path(value: object) -> str:
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
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be a non-empty string")
            continue
        result.append(item)
    if len(result) != len(set(result)):
        errors.append(f"{label} contains duplicates")
    return result


def _open_gaps(construction: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = construction.get("gap_register")
    if not isinstance(raw, list):
        return {}
    return {
        item["id"]: item
        for item in raw
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item.get("status") == "open"
    }


def _planes(construction: dict[str, Any]) -> set[str]:
    raw = construction.get("planes")
    if not isinstance(raw, list):
        return set()
    return {
        item["id"]
        for item in raw
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _validate_links(
    topology: dict[str, Any],
    architecture: dict[str, Any],
    construction: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> None:
    if topology.get("schema_version") != 1:
        errors.append("state topology schema_version must be exactly 1")
    if topology.get("status") != "active":
        errors.append("state topology status must be active")

    version = topology.get("topology_version")
    if not isinstance(version, str) or not version:
        errors.append("topology_version must be a non-empty string")

    architecture_tag = architecture.get("architecture_tag")
    if topology.get("architecture_tag") != architecture_tag:
        errors.append(
            "state topology architecture_tag must exactly match machine/architecture.json"
        )
    if construction.get("architecture_tag") != architecture_tag:
        errors.append(
            "construction architecture_tag must exactly match machine/architecture.json"
        )

    expected_links = {
        "architecture_contract": ARCHITECTURE_PATH.as_posix(),
        "construction_contract": CONSTRUCTION_PATH.as_posix(),
        "human_manual": "docs/AI_APP_CONSTRUCTION_MANUAL.md",
        "validator": "scripts/check_state_topology.py",
    }
    for key, expected in expected_links.items():
        if topology.get(key) != expected:
            errors.append(f"state topology {key} must be {expected!r}")
        if not (repo_root / expected).exists():
            errors.append(f"state topology linked path is missing: {expected}")

    construction_link = construction.get("state_topology")
    if not isinstance(construction_link, dict):
        errors.append("construction contract must link state_topology")
    else:
        if construction_link.get("contract") != TOPOLOGY_PATH.as_posix():
            errors.append("construction state_topology.contract path drift")
        if construction_link.get("validator") != "scripts/check_state_topology.py":
            errors.append("construction state_topology.validator path drift")


def _validate_physical_stores(
    topology: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    raw = topology.get("physical_stores")
    if not isinstance(raw, list) or not raw:
        errors.append("physical_stores must be a non-empty list")
        return {}

    stores: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw):
        label = f"physical_stores[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        store_id = item.get("id")
        if not isinstance(store_id, str) or not store_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if store_id in stores:
            errors.append(f"duplicate physical store id: {store_id}")
            continue
        stores[store_id] = item

        for key in (
            "technology",
            "durability",
            "production_role",
            "network",
            "authentication",
            "backup",
            "restore",
            "migration",
        ):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f"physical store {store_id}.{key} must be non-empty")

        volumes = _strings(
            item.get("volumes"),
            label=f"physical store {store_id}.volumes",
            errors=errors,
            allow_empty=True,
        )
        del volumes

        evidence = _strings(
            item.get("evidence"),
            label=f"physical store {store_id}.evidence",
            errors=errors,
        )
        for relative in evidence:
            try:
                normalized = _path(relative)
            except ValueError as exc:
                errors.append(f"physical store {store_id}.evidence: {exc}")
                continue
            if not (repo_root / normalized).exists():
                errors.append(
                    f"physical store {store_id} evidence path missing: {normalized}"
                )

        compose_file = item.get("compose_file")
        runtime_service = item.get("runtime_service")
        if compose_file is None:
            if runtime_service is not None:
                errors.append(
                    f"physical store {store_id} has runtime_service without compose_file"
                )
        else:
            try:
                compose_path = _path(compose_file)
            except ValueError as exc:
                errors.append(f"physical store {store_id}.compose_file: {exc}")
            else:
                full = repo_root / compose_path
                if not full.is_file():
                    errors.append(
                        f"physical store {store_id} compose file missing: {compose_path}"
                    )
                elif isinstance(runtime_service, str) and runtime_service:
                    text = full.read_text(encoding="utf-8", errors="replace")
                    marker = f"  {runtime_service}:"
                    if marker not in text:
                        errors.append(
                            f"physical store {store_id} runtime service "
                            f"{runtime_service!r} not found in {compose_path}"
                        )
                elif runtime_service is not None:
                    errors.append(
                        f"physical store {store_id}.runtime_service must be string or null"
                    )

    return stores


def _validate_state_domains(
    topology: dict[str, Any],
    construction: dict[str, Any],
    stores: dict[str, dict[str, Any]],
    repo_root: Path,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    raw = topology.get("state_domains")
    if not isinstance(raw, list) or not raw:
        errors.append("state_domains must be a non-empty list")
        return {}

    plane_ids = _planes(construction)
    open_gaps = _open_gaps(construction)
    domains: dict[str, dict[str, Any]] = {}

    for index, item in enumerate(raw):
        label = f"state_domains[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue

        domain_id = item.get("id")
        if not isinstance(domain_id, str) or not domain_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if domain_id in domains:
            errors.append(f"duplicate state domain id: {domain_id}")
            continue
        domains[domain_id] = item

        owner = item.get("owner_plane")
        if owner not in plane_ids:
            errors.append(
                f"state domain {domain_id} owner_plane references unknown plane {owner!r}"
            )

        store_id = item.get("physical_store")
        if store_id not in stores:
            errors.append(
                f"state domain {domain_id} references unknown physical store {store_id!r}"
            )

        authority = item.get("authority")
        if authority not in _AUTHORITIES:
            errors.append(
                f"state domain {domain_id}.authority must be one of "
                f"{sorted(_AUTHORITIES)}"
            )

        source = item.get("source_of_truth")
        if not isinstance(source, bool):
            errors.append(f"state domain {domain_id}.source_of_truth must be boolean")
        elif authority in _SOURCE_OF_TRUTH_AUTHORITIES and source is not True:
            errors.append(
                f"state domain {domain_id} authority {authority!r} must be source_of_truth"
            )
        elif authority in _NON_AUTHORITY_CLASSES and source is not False:
            errors.append(
                f"state domain {domain_id} authority {authority!r} must not be source_of_truth"
            )

        if not isinstance(item.get("status"), str) or not item["status"].strip():
            errors.append(f"state domain {domain_id}.status must be non-empty")

        data_classes = _strings(
            item.get("data_classes"),
            label=f"state domain {domain_id}.data_classes",
            errors=errors,
        )
        valid_classes = {
            dc.get("id")
            for dc in construction.get("data_classes", [])
            if isinstance(dc, dict)
        }
        for data_class in data_classes:
            if data_class not in valid_classes:
                errors.append(
                    f"state domain {domain_id} references unknown data class {data_class!r}"
                )

        for key in (
            "logical_location",
            "transaction_scope",
            "consistency",
            "retention",
            "backup_restore",
            "migration",
        ):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f"state domain {domain_id}.{key} must be non-empty")

        derived_from = _strings(
            item.get("derived_from"),
            label=f"state domain {domain_id}.derived_from",
            errors=errors,
            allow_empty=authority not in {"derived", "mixed-transitional", "recovery-aid"},
        )
        rebuildable = item.get("rebuildable")
        if not isinstance(rebuildable, bool):
            errors.append(f"state domain {domain_id}.rebuildable must be boolean")

        if authority == "derived":
            if not derived_from:
                errors.append(
                    f"derived state domain {domain_id} must declare upstream sources"
                )
            if rebuildable is not True:
                errors.append(
                    f"derived state domain {domain_id} must be rebuildable"
                )
        if authority == "scratch":
            if source is not False or rebuildable is not True:
                errors.append(
                    f"scratch state domain {domain_id} must be non-authoritative and rebuildable"
                )
        if authority == "recovery-aid" and source is not False:
            errors.append(
                f"recovery-aid state domain {domain_id} must not be source_of_truth"
            )

        gap_id = item.get("gap")
        if authority in {"mixed-transitional", "authoritative-unbound"}:
            if not isinstance(gap_id, str) or gap_id not in open_gaps:
                errors.append(
                    f"transitional state domain {domain_id} must reference an open gap"
                )
            elif open_gaps[gap_id].get("priority") != "P0":
                errors.append(
                    f"transitional state domain {domain_id} gap must be P0: {gap_id}"
                )
        elif gap_id is not None and gap_id not in open_gaps:
            errors.append(
                f"state domain {domain_id} references unknown/closed gap {gap_id!r}"
            )

        store = stores.get(str(store_id))
        if (
            authority in {"authoritative", "conditional-authoritative"}
            and store is not None
            and store.get("durability") == "volatile"
        ):
            errors.append(
                f"authoritative state domain {domain_id} cannot use volatile store {store_id}"
            )
        if authority == "authoritative-unbound":
            if store is not None and store.get("durability") != "unbound":
                errors.append(
                    f"authoritative-unbound domain {domain_id} must use unbound store"
                )
            if rebuildable is not False:
                errors.append(
                    f"authoritative-unbound domain {domain_id} must not claim rebuildability"
                )

        evidence = _strings(
            item.get("evidence"),
            label=f"state domain {domain_id}.evidence",
            errors=errors,
        )
        for relative in evidence:
            try:
                normalized = _path(relative)
            except ValueError as exc:
                errors.append(f"state domain {domain_id}.evidence: {exc}")
                continue
            if not (repo_root / normalized).exists():
                errors.append(
                    f"state domain {domain_id} evidence path missing: {normalized}"
                )

    for domain_id, item in domains.items():
        for source_id in item.get("derived_from", []):
            if source_id in domains:
                continue
            # Descriptive external/repository sources are allowed only for the
            # explicitly regenerable seeded-content domain.
            if domain_id == "backend-seeded-content":
                continue
            errors.append(
                f"state domain {domain_id} derived_from references unknown domain {source_id!r}"
            )

    return domains


def _validate_flows(
    topology: dict[str, Any],
    domains: dict[str, dict[str, Any]],
    errors: list[str],
) -> list[str]:
    raw = topology.get("state_flows")
    if not isinstance(raw, list) or not raw:
        errors.append("state_flows must be a non-empty list")
        return []

    ids: list[str] = []
    for index, item in enumerate(raw):
        label = f"state_flows[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        flow_id = item.get("id")
        if not isinstance(flow_id, str) or not flow_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if flow_id in ids:
            errors.append(f"duplicate state flow id: {flow_id}")
        ids.append(flow_id)

        source = item.get("from")
        target = item.get("to")
        if source not in domains:
            errors.append(f"state flow {flow_id}.from references unknown domain {source!r}")
        if target not in domains:
            errors.append(f"state flow {flow_id}.to references unknown domain {target!r}")
        if source == target:
            errors.append(f"state flow {flow_id} must cross state domains")
        for key in ("mode", "rule", "failure"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f"state flow {flow_id}.{key} must be non-empty")

    return ids


def validate_state_topology(repo_root: Path = ROOT) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    try:
        topology = _load(repo_root / TOPOLOGY_PATH)
        architecture = _load(repo_root / ARCHITECTURE_PATH)
        construction = _load(repo_root / CONSTRUCTION_PATH)
    except ValueError as exc:
        return [str(exc)], {}

    _validate_links(topology, architecture, construction, repo_root, errors)
    stores = _validate_physical_stores(topology, repo_root, errors)
    domains = _validate_state_domains(
        topology, construction, stores, repo_root, errors
    )
    flows = _validate_flows(topology, domains, errors)

    recovery_order = _strings(
        topology.get("recovery_order"),
        label="recovery_order",
        errors=errors,
    )
    invariants = _strings(
        topology.get("invariants"),
        label="invariants",
        errors=errors,
    )

    required_domains = {
        "backend-core-app-state",
        "backend-seeded-content",
        "backend-swarm-scratch",
        "canonical-operation-state",
        "backend-rag-local-chroma",
        "optional-vector-index",
        "operation-event-stream",
        "in-process-retrieval-memory",
        "manual-memory-snapshots",
    }
    missing_domains = sorted(required_domains - set(domains))
    if missing_domains:
        errors.append(
            "mandatory state domains missing: " + ", ".join(missing_domains)
        )

    mixed = sorted(
        domain_id
        for domain_id, item in domains.items()
        if item.get("authority") in {"mixed-transitional", "authoritative-unbound"}
    )
    authoritative = sorted(
        domain_id
        for domain_id, item in domains.items()
        if item.get("authority") in _SOURCE_OF_TRUTH_AUTHORITIES
    )
    derived = sorted(
        domain_id
        for domain_id, item in domains.items()
        if item.get("authority") in {"derived", "scratch", "recovery-aid"}
    )

    summary = {
        "ok": not errors,
        "architecture_tag": topology.get("architecture_tag"),
        "topology_version": topology.get("topology_version"),
        "physical_stores": len(stores),
        "state_domains": len(domains),
        "state_flows": len(flows),
        "authoritative_domains": authoritative,
        "transitional_domains": mixed,
        "derived_or_disposable_domains": derived,
        "recovery_steps": len(recovery_order),
        "invariants": len(invariants),
        "errors": errors,
    }
    return errors, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    errors, summary = validate_state_topology()
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif errors:
        print("state-topology: rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
    else:
        print(
            "state-topology: OK "
            f"(tag={summary['architecture_tag']}; "
            f"version={summary['topology_version']}; "
            f"stores={summary['physical_stores']}; "
            f"domains={summary['state_domains']}; "
            f"flows={summary['state_flows']}; "
            f"transitional={len(summary['transitional_domains'])})"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
