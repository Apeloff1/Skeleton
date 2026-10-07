"""Static governance validation for machine repository configuration."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .config import MachineConfig
from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class GovernanceViolation:
    code: str
    severity: str
    subject: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "subject": self.subject,
            "detail": self.detail,
        }


def validate_governance(
    model: RepositoryModel,
    config: MachineConfig,
) -> tuple[GovernanceViolation, ...]:
    violations: list[GovernanceViolation] = []

    prefix_owner: dict[str, str] = {}
    for rule in config.zones:
        for prefix in rule.prefixes:
            prior = prefix_owner.get(prefix)
            if prior is not None and prior != rule.name:
                violations.append(GovernanceViolation(
                    code="governance.duplicate-prefix",
                    severity="high",
                    subject=prefix,
                    detail=f"prefix is claimed by both {prior} and {rule.name}",
                ))
            prefix_owner[prefix] = rule.name

    rules = list(config.zones)
    for left_index, left in enumerate(rules):
        for right in rules[left_index + 1:]:
            for left_prefix in left.prefixes:
                for right_prefix in right.prefixes:
                    if left_prefix == right_prefix:
                        continue
                    if left_prefix.startswith(right_prefix) or right_prefix.startswith(left_prefix):
                        violations.append(GovernanceViolation(
                            code="governance.overlapping-prefix",
                            severity="medium",
                            subject=f"{left.name}:{right.name}",
                            detail=f"overlapping zone prefixes {left_prefix!r} and {right_prefix!r}",
                        ))

    declared = {rule.name for rule in config.zones}
    live = {item.name for item in model.subsystems}
    for zone in sorted(declared - live):
        violations.append(GovernanceViolation(
            code="governance.empty-declared-zone",
            severity="info",
            subject=zone,
            detail="declared zone has no live indexed subsystem",
        ))
    for zone in sorted(live - declared - {"unclassified"}):
        violations.append(GovernanceViolation(
            code="governance.implicit-live-zone",
            severity="medium",
            subject=zone,
            detail="live subsystem is not represented in machine config",
        ))

    root_names = {
        PurePosixPath(item.path).parts[0]
        for item in model.files
        if PurePosixPath(item.path).parts
    }
    suspicious = {
        name for name in root_names
        if name.casefold() in {"tmp", "temp", "misc", "old", "backup", "archive", "new"}
    }
    for name in sorted(suspicious):
        violations.append(GovernanceViolation(
            code="governance.ambiguous-root",
            severity="low",
            subject=name,
            detail="top-level directory name is weak for machine navigation",
        ))

    return tuple(sorted(
        violations,
        key=lambda item: (item.severity, item.code, item.subject),
    ))
