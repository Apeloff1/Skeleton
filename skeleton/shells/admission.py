"""Fail-closed command admission before process execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from skeleton.shells.capabilities import CapabilityGrant, ShellCapability
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.errors import ShellErrorCode, ShellErrorContext, ShellPlaneError
from skeleton.shells.runner import ShellCommand
from skeleton.shells.workspace import WorkspacePolicy


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    command: str
    required_capabilities: tuple[str, ...]
    environment_keys: tuple[str, ...]
    argument_count: int
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "command": self.command,
            "required_capabilities": list(self.required_capabilities),
            "environment_keys": list(self.environment_keys),
            "argument_count": self.argument_count,
            "reason": self.reason,
        }


class AdmissionError(ShellPlaneError):
    pass


class CommandAdmission:
    """Validate a ``ShellCommand`` against a command catalog and caller grant."""

    def __init__(self, catalog: CommandCatalog, workspace: WorkspacePolicy | None = None) -> None:
        self.catalog = catalog
        self.workspace = workspace

    def _definition(self, command: ShellCommand) -> CommandDefinition:
        try:
            return self.catalog.get(command.command)
        except KeyError as exc:
            raise AdmissionError(
                ShellErrorContext(
                    ShellErrorCode.COMMAND,
                    command=command.command,
                    detail="command is not present in the command catalog",
                )
            ) from exc

    def admit(self, command: ShellCommand, grant: CapabilityGrant) -> AdmissionDecision:
        definition = self._definition(command)
        required = set(definition.required_capabilities)
        if command.env:
            required.add(ShellCapability.CUSTOM_ENV)
        if command.stdin is not None:
            if not definition.allow_stdin:
                raise AdmissionError(
                    ShellErrorContext(
                        ShellErrorCode.CAPABILITY,
                        command=command.command,
                        detail="stdin is disabled for this command",
                    )
                )
            required.add(ShellCapability.STDIN)
        if command.allowed_returncodes != frozenset({0}):
            if not definition.allow_nonzero_success:
                raise AdmissionError(
                    ShellErrorContext(
                        ShellErrorCode.CAPABILITY,
                        command=command.command,
                        detail="nonzero success codes are disabled for this command",
                    )
                )
            required.add(ShellCapability.NONZERO_SUCCESS)
        if definition.max_timeout is not None and command.timeout is not None and command.timeout > definition.max_timeout:
            raise AdmissionError(
                ShellErrorContext(
                    ShellErrorCode.POLICY,
                    command=command.command,
                    detail="requested timeout exceeds command definition",
                )
            )
        grant.require_all(required, command=command.command)
        definition.arguments.validate(command.command, command.args)
        definition.environment.build(command.command, command.env, parent={})
        if self.workspace is not None:
            self.workspace.resolve(command.command, command.cwd)
        return AdmissionDecision(
            True,
            command.command,
            tuple(sorted(cap.value for cap in required)),
            tuple(sorted(command.env)),
            len(command.args),
        )

    def inspect(self, command: ShellCommand, grant: CapabilityGrant) -> AdmissionDecision:
        try:
            return self.admit(command, grant)
        except ShellPlaneError as exc:
            return AdmissionDecision(
                False,
                command.command,
                (),
                tuple(sorted(command.env)),
                len(command.args),
                reason=exc.context.detail or exc.context.code.value,
            )
