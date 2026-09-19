"""Command definitions bind executable authority to per-command policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping

from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.capabilities import ShellCapability
from skeleton.shells.environment import EnvironmentPolicy
from skeleton.shells.registry import ExecutableSpec


@dataclass(frozen=True)
class CommandDefinition:
    spec: ExecutableSpec
    arguments: ArgumentPolicy
    environment: EnvironmentPolicy = field(default_factory=EnvironmentPolicy.empty)
    required_capabilities: frozenset[ShellCapability] = frozenset({ShellCapability.EXECUTE})
    max_timeout: float | None = None
    allow_stdin: bool = False
    allow_nonzero_success: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        required = frozenset(self.required_capabilities)
        if ShellCapability.EXECUTE not in required:
            required = required | {ShellCapability.EXECUTE}
        if self.max_timeout is not None and self.max_timeout <= 0:
            raise ValueError("command max_timeout must be positive")
        object.__setattr__(self, "required_capabilities", required)

    @property
    def name(self) -> str:
        return self.spec.name

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "tags": sorted(self.spec.tags),
            "required_capabilities": sorted(cap.value for cap in self.required_capabilities),
            "max_timeout": self.max_timeout,
            "allow_stdin": self.allow_stdin,
            "allow_nonzero_success": self.allow_nonzero_success,
            "description": self.description,
            "environment_keys": list(self.environment.allowed_keys()),
        }


class CommandCatalog:
    """Default-deny catalog of logical command contracts."""

    def __init__(self, definitions: Iterable[CommandDefinition] = ()) -> None:
        self._definitions: dict[str, CommandDefinition] = {}
        self._frozen = False
        for definition in definitions:
            self.register(definition)

    def register(self, definition: CommandDefinition, *, replace: bool = False) -> None:
        if self._frozen:
            raise RuntimeError("command catalog is frozen")
        if definition.name in self._definitions and not replace:
            raise ValueError(f"command definition already registered: {definition.name}")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> CommandDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise KeyError(f"unknown command definition: {name!r}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    def by_tag(self, tag: str) -> tuple[CommandDefinition, ...]:
        return tuple(
            sorted(
                (definition for definition in self._definitions.values() if tag in definition.spec.tags),
                key=lambda definition: definition.name,
            )
        )

    def snapshot(self) -> tuple[CommandDefinition, ...]:
        """Return definitions in deterministic logical-name order."""
        return tuple(self._definitions[name] for name in sorted(self._definitions))

    def freeze(self) -> Mapping[str, CommandDefinition]:
        self._frozen = True
        return MappingProxyType(dict(self._definitions))

    def to_dict(self) -> dict[str, object]:
        return {name: self._definitions[name].to_dict() for name in sorted(self._definitions)}
