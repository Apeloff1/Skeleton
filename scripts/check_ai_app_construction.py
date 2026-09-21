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

    semantics = contract.get("relationship_semantics")
    if not isinstance(semantics, dict):
        errors.append("relationship_semantics must be an object")
    else:
        runtime_dependency = semantics.get("runtime_dependency")
        acceptance_target = semantics.get("acceptance_target")
        if not isinstance(runtime_dependency, dict) or runtime_dependency.get("field") != "depends_on":
            errors.append(
                "relationship_semantics.runtime_dependency.field must be depends_on"
            )
        if not isinstance(acceptance_target, dict) or acceptance_target.get("field") != "validates":
            errors.append(
                "relationship_semantics.acceptance_target.field must be validates"
            )

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

        validates = _nonempty_strings(
            plane.get("validates", []),
            label=f"plane {plane_id}.validates",
            errors=errors,
            allow_empty=True,
        )
        for target in validates:
            if target == plane_id:
                errors.append(f"plane {plane_id} must not validate itself")
            elif target not in planes:
                errors.append(
                    f"plane {plane_id} validates unknown plane {target!r}"
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
        families = _nonempty_strings(
            enforcement.get("provider_families"),
            label="runtime_enforcement.provider_families",
            errors=errors,
        )
        for required_family in ("runtime_model", "automation_model"):
            if required_family not in families:
                errors.append(
                    f"runtime_enforcement.provider_families missing {required_family}"
                )
        compatibility = _nonempty_strings(
            enforcement.get("compatibility_loaders"),
            label="runtime_enforcement.compatibility_loaders",
            errors=errors,
        )
        for relative in compatibility:
            try:
                normalized = _path(relative)
            except ValueError as exc:
                errors.append(f"runtime_enforcement.compatibility_loaders: {exc}")
                continue
            if not (repo_root / normalized).exists():
                errors.append(
                    f"provider compatibility loader is missing: {normalized}"
                )
    return must_read


def _validate_provider_declarations(
    contract: dict[str, Any],
    key: str,
    label_name: str,
    errors: list[str],
) -> list[str]:
    raw = contract.get(key)
    if not isinstance(raw, list) or not raw:
        errors.append(f"{key} must be a non-empty list")
        return []
    providers: list[str] = []
    for index, item in enumerate(raw):
        label = f"{key}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        provider_id = item.get("id")
        if not isinstance(provider_id, str) or not provider_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if provider_id in providers:
            errors.append(f"duplicate {label_name} provider: {provider_id}")
        providers.append(provider_id)
        for required in (
            "architecture_read_required",
            "construction_manual_read_required",
            "activation_receipt_required",
        ):
            if item.get(required) is not True:
                errors.append(f"provider {provider_id}.{required} must be true")
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


def _validate_provider_surfaces(
    contract: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> int:
    raw = contract.get("provider_surfaces")
    if not isinstance(raw, list) or not raw:
        errors.append("provider_surfaces must be a non-empty list")
        return 0

    bootstrap = contract.get("provider_bootstrap")
    enforcement = bootstrap.get("runtime_enforcement", {}) if isinstance(bootstrap, dict) else {}
    families = set(enforcement.get("provider_families", [])) if isinstance(enforcement, dict) else set()
    allowed_status = {"canonical", "compatibility", "transitional", "library"}
    seen_ids: set[str] = set()

    for index, item in enumerate(raw):
        label = f"provider_surfaces[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        surface_id = item.get("id")
        if not isinstance(surface_id, str) or not surface_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if surface_id in seen_ids:
            errors.append(f"duplicate provider surface id: {surface_id}")
        seen_ids.add(surface_id)

        family = item.get("family")
        if family != "none" and family not in families:
            errors.append(
                f"provider surface {surface_id} references undeclared family {family!r}"
            )
        if item.get("status") not in allowed_status:
            errors.append(
                f"provider surface {surface_id}.status must be one of {sorted(allowed_status)}"
            )

        try:
            owner = _path(item.get("owner"))
        except ValueError as exc:
            errors.append(f"provider surface {surface_id}.owner: {exc}")
        else:
            if not (repo_root / owner).exists():
                errors.append(
                    f"provider surface {surface_id} owner path is missing: {owner}"
                )

        credential_bearing = item.get("credential_bearing")
        receipt_required = item.get("receipt_required")
        if not isinstance(credential_bearing, bool):
            errors.append(
                f"provider surface {surface_id}.credential_bearing must be boolean"
            )
        if not isinstance(receipt_required, bool):
            errors.append(
                f"provider surface {surface_id}.receipt_required must be boolean"
            )
        if credential_bearing is True and receipt_required is not True:
            errors.append(
                f"credential-bearing provider surface must require receipt: {surface_id}"
            )
        if family == "none" and credential_bearing is True:
            errors.append(
                f"credential-bearing provider surface must declare a provider family: {surface_id}"
            )

    return len(raw)


def _validate_gap_register(
    contract: dict[str, Any],
    planes: dict[str, dict[str, Any]],
    errors: list[str],
) -> dict[str, int]:
    raw = contract.get("gap_register")
    if not isinstance(raw, list):
        errors.append("gap_register must be a list")
        return {}
    seen: set[str] = set()
    by_plane: dict[str, int] = defaultdict(int)
    open_by_plane: dict[str, int] = defaultdict(int)
    p0_open = 0
    for index, item in enumerate(raw):
        label = f"gap_register[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        gap_id = item.get("id")
        plane_id = item.get("plane")
        if not isinstance(gap_id, str) or not gap_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if gap_id in seen:
            errors.append(f"duplicate gap id: {gap_id}")
        seen.add(gap_id)
        if plane_id not in planes:
            errors.append(f"gap {gap_id} references unknown plane {plane_id!r}")
            continue
        by_plane[str(plane_id)] += 1
        if item.get("status") == "open":
            open_by_plane[str(plane_id)] += 1
        if item.get("status") not in {"open", "closed"}:
            errors.append(f"gap {gap_id}.status must be open or closed")
        if item.get("priority") not in {"P0", "P1", "P2"}:
            errors.append(f"gap {gap_id}.priority must be P0, P1, or P2")
        if item.get("status") == "open" and item.get("priority") == "P0":
            p0_open += 1
        if not isinstance(item.get("gap"), str) or not item["gap"].strip():
            errors.append(f"gap {gap_id}.gap must be non-empty")
        _nonempty_strings(
            item.get("construction"),
            label=f"gap {gap_id}.construction",
            errors=errors,
        )
        _nonempty_strings(
            item.get("closure_evidence"),
            label=f"gap {gap_id}.closure_evidence",
            errors=errors,
        )

    for plane_id, plane in planes.items():
        if plane.get("state") == "partial" and open_by_plane.get(plane_id, 0) == 0:
            errors.append(f"partial plane lacks an open construction gap: {plane_id}")

    policy = contract.get("gap_closure_policy")
    if not isinstance(policy, dict):
        errors.append("gap_closure_policy must be an object")
    else:
        for key in (
            "partial_plane_requires_open_gap",
            "p0_gaps_block_sota_complete",
            "closure_requires_evidence",
            "closure_requires_state_update",
            "no_silent_gap_deletion",
        ):
            if policy.get(key) is not True:
                errors.append(f"gap_closure_policy.{key} must be true")

    return {
        "total": len(raw),
        "p0_open": p0_open,
        "planes_with_gaps": len(by_plane),
    }


def _validate_execution_roadmap(
    contract: dict[str, Any],
    errors: list[str],
) -> list[str]:
    raw = contract.get("execution_roadmap")
    gaps = contract.get("gap_register")
    if not isinstance(raw, list) or not raw:
        errors.append("execution_roadmap must be a non-empty list")
        return []
    if not isinstance(gaps, list):
        errors.append("gap_register must exist before roadmap validation")
        return []

    known_gaps = {
        gap.get("id")
        for gap in gaps
        if isinstance(gap, dict) and isinstance(gap.get("id"), str)
    }
    open_gaps = {
        gap.get("id")
        for gap in gaps
        if isinstance(gap, dict)
        and gap.get("status") == "open"
        and isinstance(gap.get("id"), str)
    }
    p0_open = {
        gap.get("id")
        for gap in gaps
        if isinstance(gap, dict)
        and gap.get("status") == "open"
        and gap.get("priority") == "P0"
        and isinstance(gap.get("id"), str)
    }

    ids: list[str] = []
    waves: list[int] = []
    scheduled: list[str] = []
    seen_ids: set[str] = set()
    seen_waves: set[int] = set()
    for index, item in enumerate(raw):
        label = f"execution_roadmap[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        wave = item.get("wave")
        wave_id = item.get("id")
        if isinstance(wave, bool) or not isinstance(wave, int) or wave < 1:
            errors.append(f"{label}.wave must be a positive integer")
            continue
        if wave in seen_waves:
            errors.append(f"duplicate roadmap wave number: {wave}")
        seen_waves.add(wave)
        waves.append(wave)
        if not isinstance(wave_id, str) or not wave_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if wave_id in seen_ids:
            errors.append(f"duplicate roadmap id: {wave_id}")
        seen_ids.add(wave_id)
        ids.append(wave_id)

        gap_ids = _nonempty_strings(
            item.get("gaps"),
            label=f"{label}.gaps",
            errors=errors,
            allow_empty=wave_id == "sota-closure",
        )
        for gap_id in gap_ids:
            if gap_id not in known_gaps:
                errors.append(f"roadmap {wave_id} references unknown gap {gap_id!r}")
            scheduled.append(gap_id)

        if not isinstance(item.get("goal"), str) or not item["goal"].strip():
            errors.append(f"{label}.goal must be non-empty")
        _nonempty_strings(
            item.get("exit"),
            label=f"{label}.exit",
            errors=errors,
        )

        dependencies = item.get("depends_on", [])
        dep_ids = _nonempty_strings(
            dependencies,
            label=f"{label}.depends_on",
            errors=errors,
            allow_empty=True,
        )
        prior_ids = set(ids[:-1])
        for dependency in dep_ids:
            if dependency not in prior_ids:
                errors.append(
                    f"roadmap {wave_id} dependency must reference a prior wave: {dependency}"
                )

    if sorted(waves) != list(range(1, len(waves) + 1)):
        errors.append(f"roadmap wave numbers must be contiguous from one: {sorted(waves)}")

    duplicates = sorted(
        gap_id for gap_id in set(scheduled) if scheduled.count(gap_id) > 1
    )
    if duplicates:
        errors.append("open gaps scheduled more than once: " + ", ".join(duplicates))
    missing = sorted(open_gaps - set(scheduled))
    if missing:
        errors.append("open gaps missing from execution roadmap: " + ", ".join(missing))

    closure_index = next(
        (i for i, item in enumerate(raw) if isinstance(item, dict) and item.get("id") == "sota-closure"),
        None,
    )
    if closure_index is None:
        errors.append("execution roadmap must end in sota-closure")
    elif closure_index != len(raw) - 1:
        errors.append("sota-closure must be the final roadmap wave")
    else:
        scheduled_before_closure = {
            gap_id
            for item in raw[:closure_index]
            if isinstance(item, dict)
            for gap_id in item.get("gaps", [])
            if isinstance(gap_id, str)
        }
        missing_p0 = sorted(p0_open - scheduled_before_closure)
        if missing_p0:
            errors.append(
                "P0 gaps must be scheduled before SOTA closure: " + ", ".join(missing_p0)
            )

    policy = contract.get("roadmap_policy")
    if not isinstance(policy, dict):
        errors.append("roadmap_policy must be an object")
    else:
        for key in (
            "open_gap_must_be_scheduled",
            "dependencies_must_reference_prior_waves",
            "p0_before_sota_closure",
            "parallelism_allowed_only_when_dependencies_are_independent",
        ):
            if policy.get(key) is not True:
                errors.append(f"roadmap_policy.{key} must be true")

    return ids


def _validate_construction_ledger(
    contract: dict[str, Any],
    planes: dict[str, dict[str, Any]],
    repo_root: Path,
    errors: list[str],
) -> dict[str, int]:
    lifecycle = contract.get("request_lifecycle")
    lifecycle_count = 0
    if not isinstance(lifecycle, list) or not lifecycle:
        errors.append("request_lifecycle must be a non-empty list")
    else:
        lifecycle_count = len(lifecycle)
        orders: list[int] = []
        ids: set[str] = set()
        for index, item in enumerate(lifecycle):
            label = f"request_lifecycle[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            stage_id = item.get("id")
            order = item.get("order")
            owner = item.get("owner_plane")
            if not isinstance(stage_id, str) or not stage_id:
                errors.append(f"{label}.id must be non-empty")
            elif stage_id in ids:
                errors.append(f"duplicate request lifecycle id: {stage_id}")
            else:
                ids.add(stage_id)
            if isinstance(order, bool) or not isinstance(order, int) or order < 0:
                errors.append(f"{label}.order must be a non-negative integer")
            else:
                orders.append(order)
            if owner not in planes:
                errors.append(f"{label}.owner_plane references unknown plane {owner!r}")
            for key in ("input", "output", "failure"):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    errors.append(f"{label}.{key} must be non-empty")
        if sorted(orders) != list(range(len(orders))):
            errors.append(
                f"request lifecycle orders must be contiguous from zero: {sorted(orders)}"
            )

    data_classes = contract.get("data_classes")
    data_class_count = 0
    if not isinstance(data_classes, list) or not data_classes:
        errors.append("data_classes must be a non-empty list")
    else:
        data_class_count = len(data_classes)
        ids: set[str] = set()
        ranks: list[int] = []
        for index, item in enumerate(data_classes):
            label = f"data_classes[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            class_id = item.get("id")
            rank = item.get("rank")
            if not isinstance(class_id, str) or not class_id:
                errors.append(f"{label}.id must be non-empty")
            elif class_id in ids:
                errors.append(f"duplicate data class id: {class_id}")
            else:
                ids.add(class_id)
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 0:
                errors.append(f"{label}.rank must be a non-negative integer")
            else:
                ranks.append(rank)
            for key in ("description", "provider_transfer", "logging"):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    errors.append(f"{label}.{key} must be non-empty")
        if sorted(ranks) != list(range(len(ranks))):
            errors.append(
                f"data class ranks must be contiguous from zero: {sorted(ranks)}"
            )

    trust_zones = contract.get("trust_zones")
    trust_zone_count = 0
    if not isinstance(trust_zones, list) or not trust_zones:
        errors.append("trust_zones must be a non-empty list")
    else:
        trust_zone_count = len(trust_zones)
        ids: set[str] = set()
        for index, item in enumerate(trust_zones):
            label = f"trust_zones[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            zone_id = item.get("id")
            if not isinstance(zone_id, str) or not zone_id:
                errors.append(f"{label}.id must be non-empty")
            elif zone_id in ids:
                errors.append(f"duplicate trust zone id: {zone_id}")
            else:
                ids.add(zone_id)
            _nonempty_strings(
                item.get("owners"),
                label=f"{label}.owners",
                errors=errors,
            )
            _nonempty_strings(
                item.get("boundaries"),
                label=f"{label}.boundaries",
                errors=errors,
            )
            if not isinstance(item.get("trust"), str) or not item["trust"].strip():
                errors.append(f"{label}.trust must be non-empty")
            may_hold = item.get("may_hold_secrets")
            if not isinstance(may_hold, (bool, str)):
                errors.append(f"{label}.may_hold_secrets must be boolean or policy string")
        for required in (
            "human-client",
            "application-api",
            "engine-runtime",
            "data-plane",
            "external-provider",
            "tool-sandbox",
            "repository-automation",
        ):
            if required not in ids:
                errors.append(f"mandatory trust zone missing: {required}")

    profiles = contract.get("environment_profiles")
    environment_count = 0
    if not isinstance(profiles, list) or not profiles:
        errors.append("environment_profiles must be a non-empty list")
    else:
        environment_count = len(profiles)
        ids: set[str] = set()
        for index, item in enumerate(profiles):
            label = f"environment_profiles[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            profile_id = item.get("id")
            if not isinstance(profile_id, str) or not profile_id:
                errors.append(f"{label}.id must be non-empty")
                continue
            if profile_id in ids:
                errors.append(f"duplicate environment profile: {profile_id}")
            ids.add(profile_id)
            for key in (
                "network",
                "secrets",
                "durability",
                "provider_policy",
                "release_authority",
            ):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    errors.append(f"{label}.{key} must be non-empty")
        required_profiles = {"development", "ci", "staging", "production"}
        if ids != required_profiles:
            errors.append(
                "environment profiles must be exactly development, ci, staging, production"
            )

    envelopes = contract.get("canonical_envelopes")
    envelope_count = 0
    if not isinstance(envelopes, dict) or not envelopes:
        errors.append("canonical_envelopes must be a non-empty object")
    else:
        envelope_count = len(envelopes)
        for envelope_id, item in envelopes.items():
            label = f"canonical_envelopes.{envelope_id}"
            if not isinstance(envelope_id, str) or not envelope_id:
                errors.append("canonical envelope id must be non-empty")
                continue
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            owner = item.get("owner_plane")
            if owner not in planes:
                errors.append(f"{label}.owner_plane references unknown plane {owner!r}")
            _nonempty_strings(
                item.get("required_fields"),
                label=f"{label}.required_fields",
                errors=errors,
            )
        for required in (
            "operation",
            "provider_request",
            "route_decision",
            "evidence",
            "tool_receipt",
            "artifact",
            "stream_event",
            "release_evidence",
        ):
            if required not in envelopes:
                errors.append(f"mandatory canonical envelope missing: {required}")

    evidence_bundle = _nonempty_strings(
        contract.get("release_evidence_bundle"),
        label="release_evidence_bundle",
        errors=errors,
    )

    gaps = contract.get("gap_register")
    roadmap = contract.get("execution_roadmap")
    work_packages = contract.get("construction_work_packages")
    work_package_count = 0
    known_gaps = {
        item.get("id")
        for item in gaps
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    } if isinstance(gaps, list) else set()
    open_gaps = {
        item.get("id")
        for item in gaps
        if isinstance(item, dict)
        and item.get("status") == "open"
        and isinstance(item.get("id"), str)
    } if isinstance(gaps, list) else set()
    gap_wave: dict[str, int] = {}
    if isinstance(roadmap, list):
        for wave in roadmap:
            if not isinstance(wave, dict) or not isinstance(wave.get("wave"), int):
                continue
            for gap_id in wave.get("gaps", []):
                if isinstance(gap_id, str):
                    gap_wave[gap_id] = wave["wave"]

    if not isinstance(work_packages, list) or not work_packages:
        errors.append("construction_work_packages must be a non-empty list")
    else:
        work_package_count = len(work_packages)
        ids: set[str] = set()
        scheduled_gaps: list[str] = []
        for index, item in enumerate(work_packages):
            label = f"construction_work_packages[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            package_id = item.get("id")
            gap_id = item.get("gap")
            wave = item.get("wave")
            if not isinstance(package_id, str) or not package_id:
                errors.append(f"{label}.id must be non-empty")
            elif package_id in ids:
                errors.append(f"duplicate construction work package: {package_id}")
            else:
                ids.add(package_id)
            if gap_id not in known_gaps:
                errors.append(f"{label}.gap references unknown gap {gap_id!r}")
            elif isinstance(gap_id, str):
                scheduled_gaps.append(gap_id)
                expected_wave = gap_wave.get(gap_id)
                if expected_wave is not None and wave != expected_wave:
                    errors.append(
                        f"work package {package_id} wave {wave!r} does not match roadmap wave {expected_wave}"
                    )
            if isinstance(wave, bool) or not isinstance(wave, int) or wave < 1:
                errors.append(f"{label}.wave must be a positive integer")
            owners = _nonempty_strings(
                item.get("owners"),
                label=f"{label}.owners",
                errors=errors,
            )
            for owner in owners:
                try:
                    relative = _path(owner)
                except ValueError as exc:
                    errors.append(f"{label}.owners: {exc}")
                    continue
                if not (repo_root / relative).exists():
                    errors.append(f"work package owner path missing: {relative}")
            _nonempty_strings(
                item.get("steps"),
                label=f"{label}.steps",
                errors=errors,
            )
            _nonempty_strings(
                item.get("tests"),
                label=f"{label}.tests",
                errors=errors,
            )
            for key in ("objective", "exit"):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    errors.append(f"{label}.{key} must be non-empty")

        duplicates = sorted(
            gap_id
            for gap_id in set(scheduled_gaps)
            if scheduled_gaps.count(gap_id) > 1
        )
        if duplicates:
            errors.append(
                "gaps assigned to multiple construction work packages: "
                + ", ".join(duplicates)
            )
        missing = sorted(open_gaps - set(scheduled_gaps))
        if missing:
            errors.append(
                "open gaps missing construction work packages: " + ", ".join(missing)
            )

    completion = contract.get("completion_criteria")
    if not isinstance(completion, dict):
        errors.append("completion_criteria must be an object")
    else:
        for key in ("structural_complete", "sota_complete", "prohibited_shortcuts"):
            _nonempty_strings(
                completion.get(key),
                label=f"completion_criteria.{key}",
                errors=errors,
            )

    return {
        "lifecycle_stages": lifecycle_count,
        "data_classes": data_class_count,
        "trust_zones": trust_zone_count,
        "environments": environment_count,
        "envelopes": envelope_count,
        "release_evidence_items": len(evidence_bundle),
        "work_packages": work_package_count,
    }


def _validate_operation_stream_contracts(
    contract: dict[str, Any],
    repo_root: Path,
    errors: list[str],
) -> dict[str, Any]:
    operation = contract.get("operation_contract")
    stream = contract.get("stream_protocol")
    envelopes = contract.get("canonical_envelopes")

    result = {
        "operation_owner": None,
        "stream_owner": None,
        "durable_store": None,
        "stream_schema_version": None,
    }

    if not isinstance(operation, dict):
        errors.append("operation_contract must be an object")
    else:
        try:
            owner = _path(operation.get("owner"))
        except ValueError as exc:
            errors.append(f"operation_contract.owner: {exc}")
        else:
            result["operation_owner"] = owner
            path = repo_root / owner
            if not path.is_file():
                errors.append(f"operation contract owner is missing: {owner}")
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
                for token in (
                    "class OperationEnvelope",
                    "class OperationState",
                    "OperationTransitionError",
                    "TERMINAL_OPERATION_STATES",
                ):
                    if token not in text:
                        errors.append(
                            f"operation contract owner lacks required primitive {token!r}"
                        )

        states = _nonempty_strings(
            operation.get("states"),
            label="operation_contract.states",
            errors=errors,
        )
        terminal = _nonempty_strings(
            operation.get("terminal_states"),
            label="operation_contract.terminal_states",
            errors=errors,
        )
        required_states = {
            "created",
            "validated",
            "authorized",
            "admitted",
            "running",
            "completed",
            "failed",
            "cancelled",
        }
        missing_states = sorted(required_states - set(states))
        if missing_states:
            errors.append(
                "operation_contract.states missing required states: "
                + ", ".join(missing_states)
            )
        if set(terminal) != {"completed", "failed", "cancelled"}:
            errors.append(
                "operation_contract.terminal_states must be exactly completed, failed, cancelled"
            )
        if not set(terminal).issubset(set(states)):
            errors.append("operation terminal states must be declared operation states")
        _nonempty_strings(
            operation.get("required_properties"),
            label="operation_contract.required_properties",
            errors=errors,
        )

    if not isinstance(stream, dict):
        errors.append("stream_protocol must be an object")
    else:
        try:
            owner = _path(stream.get("owner"))
        except ValueError as exc:
            errors.append(f"stream_protocol.owner: {exc}")
        else:
            result["stream_owner"] = owner
            path = repo_root / owner
            if not path.is_file():
                errors.append(f"stream protocol owner is missing: {owner}")
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
                for token in (
                    "class StreamEvent",
                    "class ReplayCursor",
                    "class OperationEventLog",
                    "StreamBackpressureError",
                    "StreamReplayGapError",
                    "StreamTerminalError",
                ):
                    if token not in text:
                        errors.append(
                            f"stream protocol owner lacks required primitive {token!r}"
                        )

        schema_version = stream.get("schema_version")
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            errors.append("stream_protocol.schema_version must be an integer")
        elif schema_version < 1:
            errors.append("stream_protocol.schema_version must be positive")
        else:
            result["stream_schema_version"] = schema_version

        if stream.get("transport_neutral") is not True:
            errors.append("stream_protocol.transport_neutral must be true")
        _nonempty_strings(
            stream.get("required_semantics"),
            label="stream_protocol.required_semantics",
            errors=errors,
        )
        _nonempty_strings(
            stream.get("persistence_semantics"),
            label="stream_protocol.persistence_semantics",
            errors=errors,
        )

        durable = stream.get("durable_reference_store")
        if not isinstance(durable, str) or ":" not in durable:
            errors.append(
                "stream_protocol.durable_reference_store must be path:Class"
            )
        else:
            relative, symbol = durable.rsplit(":", 1)
            try:
                normalized = _path(relative)
            except ValueError as exc:
                errors.append(f"stream_protocol.durable_reference_store: {exc}")
            else:
                result["durable_store"] = normalized
                path = repo_root / normalized
                if not path.is_file():
                    errors.append(f"durable stream store is missing: {normalized}")
                else:
                    text = path.read_text(encoding="utf-8", errors="replace")
                    if not symbol or f"class {symbol}" not in text:
                        errors.append(
                            "durable stream store class is missing: "
                            f"{durable}"
                        )
                    for token in (
                        "StreamReplayGapError",
                        "StreamTerminalError",
                        "StreamBackpressureError",
                        "compacted_through",
                    ):
                        if token not in text:
                            errors.append(
                                f"durable stream store lacks required semantic token {token!r}"
                            )

    if not isinstance(envelopes, dict):
        errors.append(
            "canonical_envelopes must exist for operation/stream validation"
        )
    else:
        operation_envelope = envelopes.get("operation")
        stream_envelope = envelopes.get("stream_event")
        if not isinstance(operation_envelope, dict):
            errors.append("canonical_envelopes.operation must be an object")
        else:
            fields = operation_envelope.get("required_fields")
            if not isinstance(fields, list):
                errors.append(
                    "canonical_envelopes.operation.required_fields must be a list"
                )
            else:
                required = {
                    "operation_id",
                    "tenant_id",
                    "actor_id",
                    "capability",
                    "created_at",
                    "deadline",
                    "idempotency_key",
                    "trace_id",
                }
                missing = sorted(required - set(fields))
                if missing:
                    errors.append(
                        "canonical operation envelope missing fields: "
                        + ", ".join(missing)
                    )

        if not isinstance(stream_envelope, dict):
            errors.append("canonical_envelopes.stream_event must be an object")
        else:
            fields = stream_envelope.get("required_fields")
            if not isinstance(fields, list):
                errors.append(
                    "canonical_envelopes.stream_event.required_fields must be a list"
                )
            else:
                required = {
                    "operation_id",
                    "event_id",
                    "sequence",
                    "type",
                    "timestamp",
                    "payload",
                }
                missing = sorted(required - set(fields))
                if missing:
                    errors.append(
                        "canonical stream event envelope missing fields: "
                        + ", ".join(missing)
                    )

    return result


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
    providers = _validate_provider_declarations(
        contract, "runtime_model_providers", "runtime model", errors
    )
    automation_providers = _validate_provider_declarations(
        contract, "automation_model_providers", "automation model", errors
    )
    provider_surfaces = _validate_provider_surfaces(contract, repo_root, errors)
    ledger = _validate_construction_ledger(contract, planes, repo_root, errors)
    operation_stream = _validate_operation_stream_contracts(
        contract, repo_root, errors
    )
    gates = _validate_acceptance_gates(contract, errors)
    gaps = _validate_gap_register(contract, planes, errors)
    roadmap = _validate_execution_roadmap(contract, errors)

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
        "automation_providers": automation_providers,
        "provider_surfaces": provider_surfaces,
        "construction_ledger": ledger,
        "operation_stream": operation_stream,
        "provider_documents": must_read,
        "acceptance_gates": gates,
        "gaps": gaps,
        "roadmap": roadmap,
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
            f"automation={','.join(summary['automation_providers'])}; "
            f"surfaces={summary['provider_surfaces']}; "
            f"lifecycle={summary['construction_ledger'].get('lifecycle_stages', 0)}; "
            f"work-packages={summary['construction_ledger'].get('work_packages', 0)}; "
            f"stream-schema={summary['operation_stream'].get('stream_schema_version')}; "
            f"gates={len(summary['acceptance_gates'])}; "
            f"gaps={summary['gaps'].get('total', 0)}; "
            f"p0-open={summary['gaps'].get('p0_open', 0)}; "
            f"roadmap-waves={len(summary['roadmap'])})"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
