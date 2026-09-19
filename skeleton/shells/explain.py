"""Human/machine-readable explanations of shell authority."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skeleton.shells.capabilities import CapabilityGrant
from skeleton.shells.commands import CommandCatalog
from skeleton.shells.runner import ShellPolicy


@dataclass(frozen=True)
class CommandExplanation:
    command: str
    registered: bool
    executable_authorized: bool
    caller_capabilities: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    allowed_environment_keys: tuple[str, ...]
    cwd_root_count: int
    max_timeout: float | None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "registered": self.registered,
            "executable_authorized": self.executable_authorized,
            "caller_capabilities": list(self.caller_capabilities),
            "required_capabilities": list(self.required_capabilities),
            "allowed_environment_keys": list(self.allowed_environment_keys),
            "cwd_root_count": self.cwd_root_count,
            "max_timeout": self.max_timeout,
            "description": self.description,
        }


def explain_command(
    command: str,
    *,
    catalog: CommandCatalog,
    policy: ShellPolicy,
    grant: CapabilityGrant,
) -> CommandExplanation:
    try:
        definition = catalog.get(command)
    except KeyError:
        return CommandExplanation(
            command,
            False,
            command in policy.executables,
            tuple(sorted(cap.value for cap in grant.capabilities)),
            (),
            (),
            len(policy.cwd_roots),
            None,
            "command has no registered definition",
        )
    return CommandExplanation(
        command,
        True,
        command in policy.executables,
        tuple(sorted(cap.value for cap in grant.capabilities)),
        tuple(sorted(cap.value for cap in definition.required_capabilities)),
        definition.environment.allowed_keys(),
        len(policy.cwd_roots),
        definition.max_timeout,
        definition.description,
    )
