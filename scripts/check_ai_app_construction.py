#!/usr/bin/env python3
"""Fail-closed validator for the complete AI application construction contract."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = Path("machine/ai_app_construction.json")
ARCHITECTURE_PATH = Path("machine/architecture.json")

_ALLOWED_STATES = frozenset({"present", "partial", "planned"})
_REQUIRED_PLANE_FIELDS = (
    "id",
    "owner",
    "state",
    "responsibility",
    "depends_on",
    "evidence",
    "required_interfaces",
    "construction",
    "acceptance",
    "failure_mode",
)


def _load(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"missing construction source: {path}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {path}: line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError("must be a non-empty repository-relative POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("must be normalized and repository-relative")
    if pure.as_posix() != value:
        raise ValueError("must use canonical POSIX spelling")
    return value


def _nonempty_strings(
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


def _dag_order(
    nodes: dict[str, dict[str, Any]],
    *,
    dependency_key: str,
    label: str,
    errors: list[str],
) -> list[str]:
    indegree = {node_id: 0 for node_id in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)

    for node_id, node in nodes.items():
        deps = node.get(dependency_key, [])
        if not isinstance(deps, list):
            continue
        for dependency in deps:
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
        errors.append(f"{label} dependency graph contains a cycle: {', '.join(cyclic)}")
    return order


def _validate_contract_links(
    contract: dict[str, Any],
    architecture: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> None:
    if contract.get("schema_version") != 1:
        errors.append("construction schema_version must be exactly 1")
    if contract.get("status") != "active":
        errors.append("construction status must be active")
    version = contract.get("construction_version")
    if not isinstance(version, str) or not version:
        errors.append("construction_version must be a non-empty string")

    architecture_tag = architecture.get("architecture_tag")
    if contract.get("architecture_tag") != architecture_tag:
        errors.append(
            "construction architecture_tag must exactly match machine/architecture.json"
        )
    if contract.get("architecture_contract") != ARCHITECTURE_PATH.as_posix():
        errors.append("construction architecture_contract path drift")

    for key in ("human_manual", "architecture_contract", "runtime_contract"):
        raw = contract.get(key)
        try:
            relative = _path(raw)
        except ValueError as exc:
            errors.append(f"{key}: {exc}")
            continue
        if not (repo_root / relative).exists():
            errors.append(f"{key} references missing path: {relative}")


def _validate_planes(
    contract: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    raw_planes = contract.get("planes")
    if not isinstance(raw_planes, list) or not raw_planes:
        errors.append("planes must be a non-empty list")
        return {}, []

    planes: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_planes):
        label = f"planes[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = [field for field in _REQUIRED_PLANE_FIELDS if field not in raw]
        if missing:
            errors.append(f"{label} missing fields: {', '.join(missing)}")
        plane_id = raw.get("id")
        if not isinstance(plane_id, str) or not plane_id:
            errors.append(f"{label}.id must be a non-empty string")
            continue
        if plane_id in planes:
            errors.append(f"duplicate plane id: {plane_id}")
            continue
        planes[plane_id] = raw

    for plane_id, plane in planes.items():
        owner = plane.get("owner")
        try:
            owner_path = _path(owner)
        except ValueError as exc:
            errors.append(f"plane {plane_id}.owner: {exc}")
        else:
            if not (repo_root / owner_path).exists():
                errors.append(f"plane {plane_id} owner path is missing: {owner_path}")

        state = plane.get("state")
        if state not in _ALLOWED_STATES:
            errors.append(
                f"plane {plane_id}.state must be one of {sorted(_ALLOWED_STATES)}"
            )

        responsibility = plane.get("responsibility")
        failure_mode = plane.get("failure_mode")
        if not isinstance(responsibility, str) or not responsibility.strip():
            errors.append(f"plane {plane_id}.responsibility must be non-empty")
        if not isinstance(failure_mode, str) or not failure_mode.strip():
            errors.append(f"plane {plane_id}.failure_mode must be non-empty")

        dependencies = _nonempty_strings(
            plane.get("depends_on"),
            label=f"plane {plane_id}.depends_on",
            errors=errors,
            allow_empty=True,
        )
        for dependency in dependencies:
            if dependency == plane_id:
                errors.append(f"plane {plane_id} must not depend on itself")
            elif dependency not in planes:
                errors.append(
                    f"plane {plane_id} depends on unknown plane {dependency!r}"
                )

        evidence = _nonempty_strings(
            plane.get("evidence"), label=f"plane {plane_id}.evidence", errors=errors
        )
        for item in evidence:
            try:
                relative = _path(item)
            except ValueError as exc:
                errors.append(f"plane {plane_id}.evidence: {exc}")
                continue
            if not (repo_root / relative).exists():
                errors.append(
                    f"plane {plane_id} evidence path is missing: {relative}"
                )

        _nonempty_strings(
            plane.get("required_interfaces"),
            label=f"plane {plane_id}.required_interfaces",
            errors=errors,
        )
        _nonempty_strings(
            plane.get("construction"),
            label=f"plane {plane_id}.construction",
            errors=errors,
        )
        _nonempty_strings(
            plane.get("acceptance"),
            label=f"plane {plane_id}.acceptance",
            errors=errors,
        )

    return planes, _dag_order(
        planes, dependency_key="depends_on", label="construction plane", errors=errors
    )


def _validate_phases(
    contract: dict[str, Any],
    planes: dict[str, dict[str, Any]],
    errors: list[str],
) -> list[str]:
    raw_phases = contract.get("construction_phases")
    if not isinstance(raw_phases, list) or not raw_phases:
        errors.append("construction_phases must be a non-empty list")
        return []

    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    scheduled: list[str] = []
    ordered_ids: list[tuple[int, str]] = []

    for index, raw in enumerate(raw_phases):
        label = f"construction_phases[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{label} must be an object")
            continue
        phase_id = raw.get("id")
        order = raw.get("order")
        goal = raw.get("goal")
        if not isinstance(phase_id, str) or not phase_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if phase_id in seen_ids:
            errors.append(f"duplicate construction phase id: {phase_id}")
        seen_ids.add(phase_id)
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            errors.append(f"{label}.order must be a non-negative integer")
        elif order in seen_orders:
            errors.append(f"duplicate construction phase order: {order}")
        else:
            seen_orders.add(order)
            ordered_ids.append((order, phase_id))
        if not isinstance(goal, str) or not goal.strip():
            errors.append(f"{label}.goal must be non-empty")

        phase_planes = _nonempty_strings(
            raw.get("planes"),
            label=f"{label}.planes",
            errors=errors,
            allow_empty=phase_id == "continuous-evolution",
        )
        for plane_id in phase_planes:
            if plane_id not in planes:
                errors.append(f"phase {phase_id} references unknown plane {plane_id!r}")
            scheduled.append(plane_id)
        _nonempty_strings(
            raw.get("exit_gates"),
            label=f"{label}.exit_gates",
            errors=errors,
        )

    expected_orders = list(range(len(seen_orders)))
    if sorted(seen_orders) != expected_orders:
        errors.append(
            f"construction phase orders must be contiguous from zero: {sorted(seen_orders)}"
        )

    duplicate_scheduled = sorted(
        plane_id for plane_id in set(scheduled) if scheduled.count(plane_id) > 1
    )
    if duplicate_scheduled:
        errors.append(
            "planes scheduled in multiple construction phases: "
            + ", ".join(duplicate_scheduled)
        )
    missing = sorted(set(planes) - set(scheduled))
    if missing:
        errors.append(
            "planes missing from construction phases: " + ", ".join(missing)
        )

    return [phase_id for _, phase_id in sorted(ordered_ids)]


def _validate_provider_bootstrap(
    contract: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> list[str]:
    bootstrap = contract.get("provider_bootstrap")
    if not isinstance(bootstrap, dict):
        errors.append("provider_bootstrap must be an object")
        return []
    if bootstrap.get("mandatory") is not True:
        errors.append("provider_bootstrap.mandatory must be true")
    if bootstrap.get("mode") != "fail_closed":
        errors.append("provider_bootstrap.mode must be fail_closed")

    must_read = _nonempty_strings(
        bootstrap.get("must_read"),
        label="provider_bootstrap.must_read",
        errors=errors,
    )
    for relative in must_read:
        try:
            normalized = _path(relative)
        except ValueError as exc:
            errors.append(f"provider_bootstrap.must_read: {exc}")
            continue
        if not (repo_root / normalized).exists():
            errors.append(f"mandatory provider document is missing: {normalized}")

    entries = bootstrap.get("development_provider_entrypoints")
    if not isinstance(entries, list) or not entries:
        errors.append("development_provider_entrypoints must be a non-empty list")
    else:
        seen: set[str] = set()
        for index, raw in enumerate(entries):
            label = f"development_provider_entrypoints[{index}]"
            if not isinstance(raw, dict):
                errors.append(f"{label} must be an object")
                continue
            provider = raw.get("provider")
            if not isinstance(provider, str) or not provider:
                errors.append(f"{label}.provider must be non-empty")
                continue
            if provider in seen:
                errors.append(f"duplicate development provider entrypoint: {provider}")
            seen.add(provider)
            if raw.get("required") is not True:
                errors.append(f"{label}.required must be true")
            try:
                relative = _path(raw.get("path"))
            except ValueError as exc:
                errors.append(f"{label}.path: {exc}")
                continue
            path = repo_root / relative
            if not path.exists():
                errors.append(f"development provider instruction path missing: {relative}")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for required in must_read:
                if required not in text:
                    errors.append(
                        f"{relative} does not point provider {provider} to {required}"
                    )

    enforcement = bootstrap.get("runtime_enforcement")
    if not isinstance(enforcement, dict):
        errors.append("provider_bootstrap.runtime_enforcement must be an object")
    else:
        for key in ("loader", "activation_boundary", "docker_materialization"):
            try:
                relative = _path(enforcement.get(key))
            except ValueError as exc:
                errors.append(f"runtime_enforcement.{key}: {exc}")
                continue
            if not (repo_root / relative).exists():
                errors.append(f"runtime enforcement path missing: {relative}")
        if enforcement.get("receipt_required") is not True:
            errors.append("runtime provider activation receipts must be required")
        if enforcement.get("undeclared_provider_policy") != "deny":
            errors.append("undeclared runtime provider policy must be deny")
    return must_read


def _validate_runtime_providers(
    contract: dict[str, Any],
    errors: list[str],
) -> list[str]:
    raw = contract.get("runtime_model_providers")
    if not isinstance(raw, list) or not raw:
        errors.append("runtime_model_providers must be a non-empty list")
        return []
    providers: list[str] = []
    for index, item in enumerate(raw):
        label = f"runtime_model_providers[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        provider_id = item.get("id")
        if not isinstance(provider_id, str) or not provider_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if provider_id in providers:
            errors.append(f"duplicate runtime model provider: {provider_id}")
        providers.append(provider_id)
        for key in (
            "architecture_read_required",
            "construction_manual_read_required",
            "activation_receipt_required",
        ):
            if item.get(key) is not True:
                errors.append(f"provider {provider_id}.{key} must be true")
        capabilities = _nonempty_strings(
            item.get("capabilities"),
            label=f"provider {provider_id}.capabilities",
            errors=errors,
        )
        if not capabilities:
            errors.append(f"provider {provider_id} must declare capabilities")
        if item.get("undeclared_capability_policy") != "deny":
            errors.append(
                f"provider {provider_id} undeclared_capability_policy must be deny"
            )
    return providers


def _validate_acceptance_gates(
    contract: dict[str, Any],
    errors: list[str],
) -> list[str]:
    raw = contract.get("acceptance_gates")
    if not isinstance(raw, list) or not raw:
        errors.append("acceptance_gates must be a non-empty list")
        return []
    ids: list[str] = []
    for index, item in enumerate(raw):
        label = f"acceptance_gates[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        gate_id = item.get("id")
        if not isinstance(gate_id, str) or not gate_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if gate_id in ids:
            errors.append(f"duplicate acceptance gate: {gate_id}")
        ids.append(gate_id)
        if item.get("required") is not True:
            errors.append(f"acceptance gate {gate_id} must be required")
        if not isinstance(item.get("kind"), str) or not item["kind"]:
            errors.append(f"acceptance gate {gate_id}.kind must be non-empty")
        if not isinstance(item.get("command"), str) or not item["command"].strip():
            errors.append(f"acceptance gate {gate_id}.command must be non-empty")
    for required in ("architecture-map", "construction-contract", "provider-bootstrap", "app-assembly"):
        if required not in ids:
            errors.append(f"mandatory acceptance gate missing: {required}")
    return ids


def validate_construction(repo_root: Path = ROOT) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    try:
        contract = _load(repo_root / CONTRACT_PATH)
        architecture = _load(repo_root / ARCHITECTURE_PATH)
    except ValueError as exc:
        return [str(exc)], {}

    _validate_contract_links(contract, architecture, repo_root, errors)
    planes, plane_order = _validate_planes(contract, repo_root, errors)
    phase_order = _validate_phases(contract, planes, errors)
    must_read = _validate_provider_bootstrap(contract, repo_root, errors)
    providers = _validate_runtime_providers(contract, errors)
    gates = _validate_acceptance_gates(contract, errors)

    gap_policy = contract.get("gap_policy")
    if not isinstance(gap_policy, dict):
        errors.append("gap_policy must be an object")
    else:
        for key in (
            "unknown_plane",
            "undeclared_provider",
            "undeclared_runtime_service",
            "unowned_interface",
            "missing_acceptance_gate",
        ):
            if gap_policy.get(key) != "forbidden":
                errors.append(f"gap_policy.{key} must be forbidden")

    states: dict[str, int] = defaultdict(int)
    for plane in planes.values():
        states[str(plane.get("state"))] += 1

    summary = {
        "ok": not errors,
        "architecture_tag": contract.get("architecture_tag"),
        "construction_version": contract.get("construction_version"),
        "planes": len(planes),
        "plane_order": plane_order,
        "plane_states": dict(sorted(states.items())),
        "phases": phase_order,
        "runtime_providers": providers,
        "provider_documents": must_read,
        "acceptance_gates": gates,
        "errors": errors,
    }
    return errors, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    errors, summary = validate_construction()
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif errors:
        print("ai-app-construction: rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
    else:
        states = ",".join(
            f"{key}={value}" for key, value in summary["plane_states"].items()
        )
        print(
            "ai-app-construction: OK "
            f"(tag={summary['architecture_tag']}; "
            f"version={summary['construction_version']}; "
            f"planes={summary['planes']}; states={states}; "
            f"providers={','.join(summary['runtime_providers'])}; "
            f"gates={len(summary['acceptance_gates'])})"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
