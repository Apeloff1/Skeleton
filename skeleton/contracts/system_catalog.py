"""Typed contract catalog and dependency graph for repository control planes."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ContractTier(str, Enum):
    ROOT = "root"
    PRIVILEGED = "privileged"
    SECURITY = "security"
    INTEGRATION = "integration"


@dataclass(frozen=True, slots=True)
class ContractSpec:
    contract_id: str
    checker: str
    tier: ContractTier
    depends_on: tuple[str, ...] = ()
    owns: tuple[str, ...] = ()
    evidence_version: int = 1


CATALOG = (
    ContractSpec(
        "automerge",
        "scripts/check_automerge_contract.py",
        ContractTier.PRIVILEGED,
        owns=(".github/workflows/automerge-control-plane.yml", "skeleton/pr_automation/"),
    ),
    ContractSpec(
        "runner-v2",
        "scripts/check_runner_v2_contract.py",
        ContractTier.PRIVILEGED,
        depends_on=("automerge",),
        owns=(".github/workflows/pr-automation-index.yml", "skeleton/pr_automation/runner_"),
    ),
    ContractSpec(
        "toolchain",
        "scripts/check_toolchain_contract.py",
        ContractTier.INTEGRATION,
        owns=("pyproject.toml", "backend/pyproject.toml", "scripts/quality-gates.sh"),
    ),
    ContractSpec(
        "defense-control-plane",
        "scripts/check_defense_control_plane_contract.py",
        ContractTier.SECURITY,
        depends_on=("runner-v2",),
        owns=("skeleton/security/", "skeleton/automation/control_plane.py"),
    ),
    ContractSpec(
        "merge-readiness",
        "scripts/check_merge_readiness_contract.py",
        ContractTier.ROOT,
        depends_on=("runner-v2", "toolchain", "defense-control-plane"),
        owns=(".github/workflows/merge-readiness.yml",),
    ),
)


def by_id(catalog: Iterable[ContractSpec] = CATALOG) -> dict[str, ContractSpec]:
    items = tuple(catalog)
    result = {item.contract_id: item for item in items}
    if len(result) != len(items):
        raise ValueError("duplicate contract id")
    return result


def validate_catalog(catalog: Iterable[ContractSpec] = CATALOG) -> None:
    items = tuple(catalog)
    index = by_id(items)
    checker_paths: set[str] = set()
    for item in items:
        if not item.contract_id or item.contract_id.lower() != item.contract_id:
            raise ValueError(f"non-canonical contract id: {item.contract_id!r}")
        if item.checker in checker_paths:
            raise ValueError(f"duplicate contract checker: {item.checker}")
        checker_paths.add(item.checker)
        if item.contract_id in item.depends_on:
            raise ValueError(f"self dependency: {item.contract_id}")
        missing = set(item.depends_on) - set(index)
        if missing:
            raise ValueError(f"{item.contract_id} has unknown dependencies: {sorted(missing)}")
        if item.evidence_version < 1:
            raise ValueError(f"invalid evidence version: {item.contract_id}")
        if len(item.owns) != len(set(item.owns)):
            raise ValueError(f"duplicate ownership prefix: {item.contract_id}")
    topological_order(items)


def topological_order(catalog: Iterable[ContractSpec] = CATALOG) -> tuple[ContractSpec, ...]:
    items = tuple(catalog)
    index = by_id(items)
    state: dict[str, int] = {}
    result: list[ContractSpec] = []

    def visit(contract_id: str) -> None:
        mark = state.get(contract_id, 0)
        if mark == 1:
            raise ValueError(f"contract dependency cycle at {contract_id}")
        if mark == 2:
            return
        state[contract_id] = 1
        spec = index[contract_id]
        for dependency in sorted(spec.depends_on):
            visit(dependency)
        state[contract_id] = 2
        result.append(spec)

    for contract_id in sorted(index):
        visit(contract_id)
    return tuple(result)


def impacted_contracts(paths: Iterable[str], catalog: Iterable[ContractSpec] = CATALOG) -> tuple[str, ...]:
    changed = tuple(paths)
    items = tuple(catalog)
    direct = {
        item.contract_id
        for item in items
        if any(path.startswith(prefix) for prefix in item.owns for path in changed)
    }
    reverse: dict[str, set[str]] = {}
    for item in items:
        for dependency in item.depends_on:
            reverse.setdefault(dependency, set()).add(item.contract_id)
    queue = list(direct)
    impacted = set(direct)
    while queue:
        current = queue.pop()
        for dependent in reverse.get(current, ()):
            if dependent not in impacted:
                impacted.add(dependent)
                queue.append(dependent)
    return tuple(item.contract_id for item in topological_order(items) if item.contract_id in impacted)
