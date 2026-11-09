"""Contract-aware developer command registry for VOL-194."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import sha256_json
from .operations_experience import DeveloperCommand


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    command_id: str
    argv: tuple[str, ...]
    ci_equivalent: tuple[str, ...]
    mutating: bool
    contract_digest: str

    @property
    def digest(self) -> str:
        return sha256_json({
            "command_id": self.command_id,
            "argv": list(self.argv),
            "ci_equivalent": list(self.ci_equivalent),
            "mutating": self.mutating,
            "contract_digest": self.contract_digest,
        })


class DeveloperCommandRegistry:
    """Canonical developer commands with explicit CI parity and mutation authority."""

    def __init__(self, commands: Iterable[DeveloperCommand]) -> None:
        items = tuple(commands)
        if not items:
            raise ValueError("registry requires at least one command")
        ids = [item.command_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("command ids must be unique")
        self._commands = {item.command_id: item for item in items}

    def resolve(
        self,
        command_id: str,
        *,
        contract_digest: str,
        allow_mutation: bool = False,
    ) -> CommandReceipt:
        if not isinstance(contract_digest, str) or len(contract_digest) != 64 or any(
            c not in "0123456789abcdef" for c in contract_digest
        ):
            raise ValueError("contract_digest must be lowercase sha256")
        command = self._commands.get(command_id)
        if command is None:
            raise KeyError("unknown developer command")
        if command.mutating and allow_mutation is not True:
            raise PermissionError("mutating developer command requires explicit authority")
        return CommandReceipt(
            command_id=command.command_id,
            argv=command.argv,
            ci_equivalent=command.ci_equivalent,
            mutating=command.mutating,
            contract_digest=contract_digest,
        )

    def verify_ci_parity(self, command_id: str, observed_argv: tuple[str, ...]) -> None:
        command = self._commands.get(command_id)
        if command is None:
            raise KeyError("unknown developer command")
        if tuple(observed_argv) != command.ci_equivalent:
            raise ValueError("developer command has drifted from canonical CI equivalent")

    def inventory(self) -> tuple[DeveloperCommand, ...]:
        return tuple(self._commands[key] for key in sorted(self._commands))
