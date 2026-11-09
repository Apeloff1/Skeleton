"""Non-executing preflight analysis for shell commands and pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from skeleton.shells.admission import CommandAdmission
from skeleton.shells.capabilities import CapabilityGrant
from skeleton.shells.pipeline import PipelineSpec
from skeleton.shells.runner import ShellCommand


@dataclass(frozen=True)
class PreflightItem:
    item_id: str
    command: str
    allowed: bool
    reason: str = ""
    argument_count: int = 0
    env_key_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "command": self.command,
            "allowed": self.allowed,
            "reason": self.reason,
            "argument_count": self.argument_count,
            "env_key_count": self.env_key_count,
        }


@dataclass(frozen=True)
class PreflightReport:
    allowed: bool
    items: tuple[PreflightItem, ...]
    command_counts: Mapping[str, int]
    total_arguments: int
    total_env_keys: int

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "items": [item.to_dict() for item in self.items],
            "command_counts": dict(self.command_counts),
            "total_arguments": self.total_arguments,
            "total_env_keys": self.total_env_keys,
        }


class PreflightAnalyzer:
    def __init__(self, admission: CommandAdmission) -> None:
        self.admission = admission

    def commands(
        self,
        commands: Iterable[tuple[str, ShellCommand]],
        grant: CapabilityGrant,
    ) -> PreflightReport:
        items: list[PreflightItem] = []
        counts: dict[str, int] = {}
        total_args = 0
        total_env = 0
        for item_id, command in commands:
            decision = self.admission.inspect(command, grant)
            items.append(
                PreflightItem(
                    item_id,
                    command.command,
                    decision.allowed,
                    decision.reason,
                    len(command.args),
                    len(command.env),
                )
            )
            counts[command.command] = counts.get(command.command, 0) + 1
            total_args += len(command.args)
            total_env += len(command.env)
        return PreflightReport(
            all(item.allowed for item in items),
            tuple(items),
            dict(sorted(counts.items())),
            total_args,
            total_env,
        )

    def pipeline(self, spec: PipelineSpec, grant: CapabilityGrant) -> PreflightReport:
        return self.commands(((step.step_id, step.command) for step in spec.steps), grant)
