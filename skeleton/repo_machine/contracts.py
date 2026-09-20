"""Derived subsystem boundary contracts for machine-safe repository growth."""
from __future__ import annotations

from dataclasses import dataclass

from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class SubsystemContract:
    zone: str
    owner: str
    criticality: str
    allowed_dependencies: tuple[str, ...]
    current_dependents: tuple[str, ...]
    requires_tests: bool
    entrypoints: tuple[str, ...]
    violations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "zone": self.zone,
            "owner": self.owner,
            "criticality": self.criticality,
            "allowed_dependencies": list(self.allowed_dependencies),
            "current_dependents": list(self.current_dependents),
            "requires_tests": self.requires_tests,
            "entrypoints": list(self.entrypoints),
            "violations": list(self.violations),
        }


def derive_contracts(model: RepositoryModel) -> tuple[SubsystemContract, ...]:
    cycles = {
        zone
        for cycle in model.cycles
        for zone in cycle
    }
    contracts: list[SubsystemContract] = []
    for subsystem in model.subsystems:
        violations: list[str] = []
        requires_tests = subsystem.code_files > 0 and subsystem.criticality in {"high", "critical"}
        if requires_tests and subsystem.test_files == 0:
            violations.append("required local test surface missing")
        if subsystem.name in cycles:
            violations.append("participates in a cross-zone dependency cycle")
        if subsystem.name == "unclassified" and subsystem.file_count:
            violations.append("zone is implicit rather than declared")
        if subsystem.file_count and not subsystem.languages:
            violations.append("zone has no classified machine language surface")
        contracts.append(SubsystemContract(
            zone=subsystem.name,
            owner=subsystem.owner,
            criticality=subsystem.criticality,
            allowed_dependencies=tuple(sorted(subsystem.dependencies)),
            current_dependents=tuple(sorted(subsystem.dependents)),
            requires_tests=requires_tests,
            entrypoints=subsystem.entrypoints,
            violations=tuple(violations),
        ))
    return tuple(sorted(contracts, key=lambda item: item.zone))


def contract_map(model: RepositoryModel) -> dict[str, dict[str, object]]:
    return {
        contract.zone: contract.as_dict()
        for contract in derive_contracts(model)
    }
