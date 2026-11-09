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
    consumes_evidence: tuple[tuple[str, int], ...] = ()
    privileges: tuple[str, ...] = ()
    maturity: int = 1
    supersedes: tuple[str, ...] = ()


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
        if (
            not isinstance(item.evidence_version, int)
            or isinstance(item.evidence_version, bool)
            or item.evidence_version < 1
        ):
            raise ValueError(f"invalid evidence version: {item.contract_id}")
        consumed_names: set[str] = set()
        for producer, version in item.consumes_evidence:
            if producer in consumed_names:
                raise ValueError(f"duplicate evidence dependency: {item.contract_id}:{producer}")
            consumed_names.add(producer)
            if producer not in item.depends_on:
                raise ValueError(
                    f"{item.contract_id} consumes evidence from non-dependency: {producer}"
                )
            if not isinstance(version, int) or isinstance(version, bool) or version < 1:
                raise ValueError(f"invalid consumed evidence version: {item.contract_id}:{producer}")
            if producer in index and index[producer].evidence_version != version:
                raise ValueError(
                    f"evidence version mismatch: {producer} produces "
                    f"{index[producer].evidence_version}, {item.contract_id} requires {version}"
                )
        if len(item.owns) != len(set(item.owns)):
            raise ValueError(f"duplicate ownership prefix: {item.contract_id}")
        if not isinstance(item.maturity, int) or isinstance(item.maturity, bool) or item.maturity < 1:
            raise ValueError(f"invalid contract maturity: {item.contract_id}")
        if len(item.supersedes) != len(set(item.supersedes)):
            raise ValueError(f"duplicate supersession: {item.contract_id}")
        if item.contract_id in item.supersedes:
            raise ValueError(f"self supersession: {item.contract_id}")
        unknown_superseded = set(item.supersedes) - set(index)
        if unknown_superseded:
            raise ValueError(
                f"{item.contract_id} supersedes unknown contracts: {sorted(unknown_superseded)}"
            )
        if len(item.privileges) != len(set(item.privileges)):
            raise ValueError(f"duplicate privilege: {item.contract_id}")
        for privilege in item.privileges:
            if not privilege or privilege.lower() != privilege or any(
                char not in "abcdefghijklmnopqrstuvwxyz0123456789:-_" for char in privilege
            ):
                raise ValueError(f"invalid privilege: {item.contract_id}:{privilege!r}")
    topological_order(items)
    cycles = supersession_cycles(items)
    if cycles:
        raise ValueError(f"contract supersession cycle: {cycles!r}")


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


@dataclass(frozen=True, slots=True)
class ContractAudit:
    execution_order: tuple[str, ...]
    ownership_conflicts: tuple[tuple[str, str, str], ...]
    orphan_dependencies: tuple[str, ...]
    privilege_escalations: tuple[tuple[str, str, str], ...]

    @property
    def clean(self) -> bool:
        return (
            not self.ownership_conflicts
            and not self.orphan_dependencies
            and not self.privilege_escalations
        )


def ownership_conflicts(
    catalog: Iterable[ContractSpec] = CATALOG,
) -> tuple[tuple[str, str, str], ...]:
    """Return ambiguous exact ownership declarations across contracts.

    Prefix overlap is intentionally legal: root contracts may cover a broad
    plane while a privileged child owns a narrower surface. Exact duplicate
    prefixes are rejected because they make the authoritative owner ambiguous.
    """
    owners: dict[str, str] = {}
    conflicts: list[tuple[str, str, str]] = []
    for item in catalog:
        for prefix in item.owns:
            previous = owners.get(prefix)
            if previous is not None and previous != item.contract_id:
                conflicts.append((prefix, previous, item.contract_id))
            else:
                owners[prefix] = item.contract_id
    return tuple(sorted(conflicts))


def dependency_closure(
    contract_id: str,
    catalog: Iterable[ContractSpec] = CATALOG,
) -> tuple[str, ...]:
    items = tuple(catalog)
    index = by_id(items)
    if contract_id not in index:
        raise KeyError(contract_id)
    found: set[str] = set()

    def collect(name: str) -> None:
        for dependency in index[name].depends_on:
            if dependency not in found:
                found.add(dependency)
                collect(dependency)

    collect(contract_id)
    order = topological_order(items)
    return tuple(item.contract_id for item in order if item.contract_id in found)


def audit_catalog(
    catalog: Iterable[ContractSpec] = CATALOG,
) -> ContractAudit:
    items = tuple(catalog)
    validate_catalog(items)
    order = topological_order(items)
    index = by_id(items)
    orphan_dependencies = tuple(
        sorted(
            dependency
            for item in items
            for dependency in item.depends_on
            if dependency not in index
        )
    )
    return ContractAudit(
        execution_order=tuple(item.contract_id for item in order),
        ownership_conflicts=ownership_conflicts(items),
        orphan_dependencies=orphan_dependencies,
        privilege_escalations=privilege_escalations(items),
    )


def privilege_escalations(
    catalog: Iterable[ContractSpec] = CATALOG,
) -> tuple[tuple[str, str, str], ...]:
    """Detect child contracts claiming privileges absent from every dependency.

    Root and standalone contracts establish trust boundaries. A dependent
    contract may retain or narrow inherited privileges but may not silently
    introduce a new privilege without making that authority explicit at a root.
    """
    items = tuple(catalog)
    index = by_id(items)
    findings: list[tuple[str, str, str]] = []
    for item in items:
        if not item.depends_on:
            continue
        inherited = {
            privilege
            for dependency in dependency_closure(item.contract_id, items)
            for privilege in index[dependency].privileges
        }
        for privilege in item.privileges:
            if privilege not in inherited:
                findings.append((item.contract_id, privilege, "not-inherited"))
    return tuple(sorted(findings))


def unowned_paths(
    paths: Iterable[str],
    catalog: Iterable[ContractSpec] = CATALOG,
) -> tuple[str, ...]:
    """Return changed control-plane paths with no declared contract owner."""
    items = tuple(catalog)
    candidates = tuple(
        path for path in paths
        if path.startswith(("scripts/check_", ".github/workflows/", "skeleton/contracts/"))
    )
    return tuple(sorted(
        path
        for path in candidates
        if not any(path.startswith(prefix) for item in items for prefix in item.owns)
        and path != "scripts/check_contract_system.py"
    ))


def supersession_cycles(
    catalog: Iterable[ContractSpec] = CATALOG,
) -> tuple[tuple[str, ...], ...]:
    items = tuple(catalog)
    index = by_id(items)
    state: dict[str, int] = {}
    stack: list[str] = []
    cycles: set[tuple[str, ...]] = set()

    def visit(name: str) -> None:
        mark = state.get(name, 0)
        if mark == 2:
            return
        if mark == 1:
            if name in stack:
                start = stack.index(name)
                cycle = tuple(stack[start:] + [name])
                cycles.add(cycle)
            return
        state[name] = 1
        stack.append(name)
        for old in sorted(index[name].supersedes):
            visit(old)
        stack.pop()
        state[name] = 2

    for name in sorted(index):
        visit(name)
    return tuple(sorted(cycles))


def active_contracts(
    catalog: Iterable[ContractSpec] = CATALOG,
) -> tuple[ContractSpec, ...]:
    items = tuple(catalog)
    superseded = {old for item in items for old in item.supersedes}
    return tuple(item for item in topological_order(items) if item.contract_id not in superseded)


def contract_fingerprint(
    spec: ContractSpec,
) -> str:
    """Stable identity for one contract's declarative authority."""
    import hashlib
    import json

    payload = {
        "contract_id": spec.contract_id,
        "checker": spec.checker,
        "tier": spec.tier.value,
        "depends_on": sorted(spec.depends_on),
        "owns": sorted(spec.owns),
        "evidence_version": spec.evidence_version,
        "consumes_evidence": sorted([list(item) for item in spec.consumes_evidence]),
        "privileges": sorted(spec.privileges),
        "maturity": spec.maturity,
        "supersedes": sorted(spec.supersedes),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def contract_fingerprints(
    catalog: Iterable[ContractSpec] = CATALOG,
) -> dict[str, str]:
    items = tuple(catalog)
    validate_catalog(items)
    return {
        item.contract_id: contract_fingerprint(item)
        for item in sorted(items, key=lambda value: value.contract_id)
    }


def authority_paths(
    contract_id: str,
    catalog: Iterable[ContractSpec] = CATALOG,
) -> tuple[tuple[str, ...], ...]:
    """Enumerate bounded dependency paths from roots to a contract."""
    items = tuple(catalog)
    index = by_id(items)
    if contract_id not in index:
        raise KeyError(contract_id)
    paths: list[tuple[str, ...]] = []

    def walk(name: str, suffix: tuple[str, ...]) -> None:
        spec = index[name]
        current = (name,) + suffix
        if not spec.depends_on:
            paths.append(current)
            return
        for dependency in sorted(spec.depends_on):
            walk(dependency, current)

    walk(contract_id, ())
    return tuple(sorted(paths))


def validate_authority_paths(
    catalog: Iterable[ContractSpec] = CATALOG,
) -> None:
    """Require every dependent contract to have a finite root authority path."""
    items = tuple(catalog)
    validate_catalog(items)
    for item in items:
        paths = authority_paths(item.contract_id, items)
        if not paths:
            raise ValueError(f"contract has no authority path: {item.contract_id}")
        for path in paths:
            if path[-1] != item.contract_id:
                raise ValueError(f"authority path terminus mismatch: {path!r}")


@dataclass(frozen=True, slots=True)
class ContractChange:
    contract_id: str
    before: str | None
    after: str | None
    classification: str


def diff_contract_catalogs(
    before: Iterable[ContractSpec],
    after: Iterable[ContractSpec],
) -> tuple[ContractChange, ...]:
    """Produce deterministic semantic changes between two contract catalogs."""
    old_items = tuple(before)
    new_items = tuple(after)
    validate_catalog(old_items)
    validate_catalog(new_items)
    old = by_id(old_items)
    new = by_id(new_items)
    changes: list[ContractChange] = []
    for contract_id in sorted(set(old) | set(new)):
        old_spec = old.get(contract_id)
        new_spec = new.get(contract_id)
        if old_spec is None and new_spec is not None:
            changes.append(
                ContractChange(contract_id, None, contract_fingerprint(new_spec), "added")
            )
            continue
        if old_spec is not None and new_spec is None:
            changes.append(
                ContractChange(contract_id, contract_fingerprint(old_spec), None, "removed")
            )
            continue
        assert old_spec is not None and new_spec is not None
        before_digest = contract_fingerprint(old_spec)
        after_digest = contract_fingerprint(new_spec)
        if before_digest == after_digest:
            continue
        old_priv = set(old_spec.privileges)
        new_priv = set(new_spec.privileges)
        old_owns = set(old_spec.owns)
        new_owns = set(new_spec.owns)
        if new_priv - old_priv:
            classification = "privilege-expanded"
        elif new_owns - old_owns:
            classification = "ownership-expanded"
        elif new_spec.evidence_version != old_spec.evidence_version:
            classification = "evidence-version-changed"
        elif new_spec.maturity < old_spec.maturity:
            classification = "maturity-regressed"
        else:
            classification = "modified"
        changes.append(
            ContractChange(contract_id, before_digest, after_digest, classification)
        )
    return tuple(changes)


def high_risk_changes(
    changes: Iterable[ContractChange],
) -> tuple[ContractChange, ...]:
    risky = {
        "added",
        "removed",
        "privilege-expanded",
        "ownership-expanded",
        "evidence-version-changed",
        "maturity-regressed",
    }
    return tuple(change for change in changes if change.classification in risky)


@dataclass(frozen=True, slots=True)
class ReviewRequirement:
    contract_id: str
    reasons: tuple[str, ...]
    required_gates: tuple[str, ...]
    human_review: bool


def review_requirements(
    changes: Iterable[ContractChange],
) -> tuple[ReviewRequirement, ...]:
    """Map semantic drift to deterministic escalation requirements."""
    gate_map = {
        "added": ("contract-system", "merge-readiness"),
        "removed": ("contract-system", "merge-readiness"),
        "privilege-expanded": ("contract-system", "workflow-input-security", "merge-readiness"),
        "ownership-expanded": ("contract-system", "repository-hygiene", "merge-readiness"),
        "evidence-version-changed": ("contract-system", "merge-readiness"),
        "maturity-regressed": ("contract-system", "merge-readiness"),
    }
    human_classes = {
        "removed",
        "privilege-expanded",
        "ownership-expanded",
        "evidence-version-changed",
        "maturity-regressed",
    }
    requirements: list[ReviewRequirement] = []
    for change in sorted(changes, key=lambda item: item.contract_id):
        gates = gate_map.get(change.classification, ("contract-system",))
        requirements.append(
            ReviewRequirement(
                contract_id=change.contract_id,
                reasons=(change.classification,),
                required_gates=tuple(sorted(set(gates))),
                human_review=change.classification in human_classes,
            )
        )
    return tuple(requirements)


def aggregate_review_policy(
    requirements: Iterable[ReviewRequirement],
) -> dict[str, object]:
    items = tuple(requirements)
    return {
        "contracts": [item.contract_id for item in items],
        "required_gates": sorted(
            {gate for item in items for gate in item.required_gates}
        ),
        "human_review": any(item.human_review for item in items),
        "reasons": sorted(
            {reason for item in items for reason in item.reasons}
        ),
    }
