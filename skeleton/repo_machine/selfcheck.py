"""Self-consistency validation for the repository machine plane."""
from __future__ import annotations

from dataclasses import dataclass

from .config import MachineConfig
from .contracts import derive_contracts
from .governance import validate_governance
from .model import RepositoryModel
from .shards import build_context_shards


@dataclass(frozen=True, slots=True)
class SelfCheckFinding:
    code: str
    severity: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "detail": self.detail,
        }


def run_selfcheck(
    model: RepositoryModel,
    config: MachineConfig,
) -> tuple[SelfCheckFinding, ...]:
    findings: list[SelfCheckFinding] = []
    subsystem_names = {item.name for item in model.subsystems}
    file_zones = {item.zone for item in model.files}

    missing = file_zones - subsystem_names
    for zone in sorted(missing):
        findings.append(SelfCheckFinding(
            "selfcheck.missing-subsystem",
            "critical",
            f"file zone {zone!r} is absent from subsystem inventory",
        ))

    if model.truncated:
        findings.append(SelfCheckFinding(
            "selfcheck.truncated",
            "critical",
            "repository model is truncated",
        ))

    contracts = derive_contracts(model)
    if {item.zone for item in contracts} != subsystem_names:
        findings.append(SelfCheckFinding(
            "selfcheck.contract-coverage",
            "high",
            "subsystem contracts do not cover the live subsystem set",
        ))

    shards = build_context_shards(model)
    if {item.zone for item in shards} != subsystem_names:
        findings.append(SelfCheckFinding(
            "selfcheck.shard-coverage",
            "high",
            "context shards do not cover the live subsystem set",
        ))
    if len({item.digest for item in shards}) != len(shards):
        duplicate_count = len(shards) - len({item.digest for item in shards})
        findings.append(SelfCheckFinding(
            "selfcheck.duplicate-shards",
            "medium",
            f"{duplicate_count} context shards have duplicate payload digests",
        ))

    for violation in validate_governance(model, config):
        if violation.severity not in {"high", "critical"}:
            continue
        findings.append(SelfCheckFinding(
            f"selfcheck.{violation.code}",
            violation.severity,
            f"{violation.subject}: {violation.detail}",
        ))

    repo_machine = next(
        (item for item in model.subsystems if item.name == "repo-machine"),
        None,
    )
    if repo_machine is None:
        findings.append(SelfCheckFinding(
            "selfcheck.machine-zone-missing",
            "high",
            "repository machine plane is not a first-class machine zone",
        ))
    elif repo_machine.criticality != "critical":
        findings.append(SelfCheckFinding(
            "selfcheck.machine-zone-criticality",
            "high",
            "repository machine plane must remain critical",
        ))

    return tuple(sorted(
        findings,
        key=lambda item: (item.severity, item.code, item.detail),
    ))


def selfcheck_ok(model: RepositoryModel, config: MachineConfig) -> bool:
    return not any(
        item.severity in {"critical", "high"}
        for item in run_selfcheck(model, config)
    )
