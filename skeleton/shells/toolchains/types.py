"""Portable logical command contracts for the policy-bound shell plane."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping

from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.capabilities import ShellCapability
from skeleton.shells.commands import CommandDefinition
from skeleton.shells.environment import EnvironmentPolicy
from skeleton.shells.registry import ExecutableSpec


class CommandEffect(str, Enum):
    READ = "read"
    WRITE = "write"
    BUILD = "build"
    TEST = "test"
    NETWORK = "network"
    PROCESS = "process"
    PACKAGE = "package"
    SOURCE_CONTROL = "source_control"
    CONTAINER = "container"
    FORMAT = "format"
    LINT = "lint"


class CommandRisk(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


@dataclass(frozen=True)
class LogicalCommandContract:
    name: str
    executable_key: str
    arguments: ArgumentPolicy
    environment: EnvironmentPolicy = field(default_factory=EnvironmentPolicy.empty)
    required_capabilities: frozenset[ShellCapability] = frozenset({ShellCapability.EXECUTE})
    max_timeout: float | None = None
    allow_stdin: bool = False
    allow_nonzero_success: bool = False
    description: str = ""
    effects: frozenset[CommandEffect] = frozenset({CommandEffect.READ})
    risk: CommandRisk = CommandRisk.LOW
    tags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.name or not self.executable_key:
            raise ValueError("contract name and executable_key are required")
        if self.max_timeout is not None and self.max_timeout <= 0:
            raise ValueError("max_timeout must be positive")
        capabilities = frozenset(self.required_capabilities) | {ShellCapability.EXECUTE}
        object.__setattr__(self, "required_capabilities", capabilities)
        object.__setattr__(self, "effects", frozenset(self.effects))
        object.__setattr__(self, "tags", frozenset(self.tags))

    def bind(self, executable_path: str) -> CommandDefinition:
        spec = ExecutableSpec(
            name=self.name,
            path=executable_path,
            capabilities=self.required_capabilities,
            tags=self.tags | frozenset(effect.value for effect in self.effects),
            description=self.description,
        )
        return CommandDefinition(
            spec=spec,
            arguments=self.arguments,
            environment=self.environment,
            required_capabilities=self.required_capabilities,
            max_timeout=self.max_timeout,
            allow_stdin=self.allow_stdin,
            allow_nonzero_success=self.allow_nonzero_success,
            description=self.description,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "executable_key": self.executable_key,
            "required_capabilities": sorted(cap.value for cap in self.required_capabilities),
            "max_timeout": self.max_timeout,
            "allow_stdin": self.allow_stdin,
            "allow_nonzero_success": self.allow_nonzero_success,
            "description": self.description,
            "effects": sorted(effect.value for effect in self.effects),
            "risk": self.risk.value,
            "tags": sorted(self.tags),
            "environment_keys": list(self.environment.allowed_keys()),
        }


@dataclass(frozen=True)
class BoundToolchain:
    definitions: tuple[CommandDefinition, ...]
    executable_paths: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "executable_paths", MappingProxyType(dict(self.executable_paths)))

    def by_name(self) -> Mapping[str, CommandDefinition]:
        return MappingProxyType({definition.name: definition for definition in self.definitions})

    def policy_executables(self) -> Mapping[str, str]:
        return MappingProxyType({definition.name: definition.spec.path for definition in self.definitions})

    def names(self) -> tuple[str, ...]:
        return tuple(definition.name for definition in self.definitions)
