"""Turn reorganization proposals into bounded reversible migration phases."""
from __future__ import annotations

from dataclasses import dataclass

from .model import RepositoryModel
from .reorganize import ReorganizationProposal


@dataclass(frozen=True, slots=True)
class MigrationPhase:
    order: int
    name: str
    objective: str
    mutation_allowed: bool
    required_evidence: tuple[str, ...]
    rollback_condition: str

    def as_dict(self) -> dict[str, object]:
        return {
            "order": self.order,
            "name": self.name,
            "objective": self.objective,
            "mutation_allowed": self.mutation_allowed,
            "required_evidence": list(self.required_evidence),
            "rollback_condition": self.rollback_condition,
        }


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    identity: str
    proposal_identity: str
    zone: str
    phases: tuple[MigrationPhase, ...]
    compatibility_required: bool
    maximum_parallel_phases: int = 1

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "proposal_identity": self.proposal_identity,
            "zone": self.zone,
            "phases": [item.as_dict() for item in self.phases],
            "compatibility_required": self.compatibility_required,
            "maximum_parallel_phases": self.maximum_parallel_phases,
        }


def build_migration_plan(
    model: RepositoryModel,
    proposal: ReorganizationProposal,
) -> MigrationPlan:
    affected = [
        item
        for item in model.files
        if item.zone == proposal.zone
        or item.path in proposal.paths
    ]
    has_code = any(item.kind == "source" for item in affected)
    has_tests = any(item.kind == "test" for item in affected)
    compatibility = proposal.category in {
        "module-decomposition",
        "dependency-boundary",
        "classification",
    }
    evidence = ["repository-machine-contract"]
    if has_code:
        evidence.append("focused-regression-tests")
    if proposal.zone in {
        item.name
        for item in model.subsystems
        if item.criticality in {"high", "critical"}
    }:
        evidence.append("integration-smoke")
    if not has_tests and has_code:
        evidence.append("characterization-tests")

    phases = (
        MigrationPhase(
            1,
            "observe",
            "Capture current imports, tests, entrypoints and machine topology.",
            False,
            tuple(evidence),
            "observation is incomplete or repository fingerprint changes",
        ),
        MigrationPhase(
            2,
            "characterize",
            "Add or identify regression coverage for behavior crossing the boundary.",
            True,
            tuple(evidence),
            "characterization checks fail",
        ),
        MigrationPhase(
            3,
            "introduce-boundary",
            proposal.objective,
            True,
            tuple(evidence),
            "new boundary breaks compatibility or introduces a dependency cycle",
        ),
        MigrationPhase(
            4,
            "redirect",
            "Move internal callers to the new canonical boundary in bounded slices.",
            True,
            tuple(evidence),
            "focused or integration validation regresses",
        ),
        MigrationPhase(
            5,
            "retire",
            "Remove obsolete internal compatibility only after no live references remain.",
            True,
            tuple(evidence),
            "machine relation graph still reports live dependents",
        ),
        MigrationPhase(
            6,
            "verify",
            "Rebuild machine topology and compare organization/evolution metrics.",
            False,
            tuple(evidence),
            "machine health or evolution report regresses materially",
        ),
    )
    return MigrationPlan(
        identity=f"migration:{proposal.identity}",
        proposal_identity=proposal.identity,
        zone=proposal.zone,
        phases=phases,
        compatibility_required=compatibility,
    )
