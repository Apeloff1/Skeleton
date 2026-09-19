"""Portable logical command contracts for the policy-bound shell plane."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.capabilities import ShellCapability
from skeleton.shells.commands import CommandDefinition
from skeleton.shells.environment import EnvironmentPolicy
from skeleton.shells.registry import ExecutableSpec


def _value_constraint_dict(value: object) -> dict[str, object]:
    return {
        "pattern": getattr(value, "pattern"),
        "choices": sorted(getattr(value, "choices")),
        "min_length": getattr(value, "min_length"),
        "max_length": getattr(value, "max_length"),
    }


def _argument_policy_dict(policy: ArgumentPolicy) -> dict[str, object]:
    return {
        "options": {
            name: {
                "name": rule.name,
                "takes_value": rule.takes_value,
                "repeatable": rule.repeatable,
                "value": _value_constraint_dict(rule.value),
            }
            for name, rule in sorted(policy.options.items())
        },
        "positional": [
            _value_constraint_dict(value)
            for value in policy.positional
        ],
        "variadic": (
            None
            if policy.variadic is None
            else _value_constraint_dict(policy.variadic)
        ),
        "min_positionals": policy.min_positionals,
        "max_positionals": policy.max_positionals,
        "allow_double_dash": policy.allow_double_dash,
        "allow_option_equals": policy.allow_option_equals,
        "deny_tokens": sorted(policy.deny_tokens),
        "deny_patterns": list(policy.deny_patterns),
        "max_total_args": policy.max_total_args,
        "max_total_bytes": policy.max_total_bytes,
        "allow_unknown_options": policy.allow_unknown_options,
    }


def _environment_policy_dict(policy: EnvironmentPolicy) -> dict[str, object]:
    return {
        "rules": {
            key: {
                "pattern": rule.pattern,
                "choices": sorted(rule.choices),
                "max_bytes": rule.max_bytes,
                "allow_empty": rule.allow_empty,
            }
            for key, rule in sorted(policy.rules.items())
        },
        "inherited": sorted(policy.inherited),
        "required": sorted(policy.required),
        "fixed": {
            key: policy.fixed[key]
            for key in sorted(policy.fixed)
        },
        "max_total_bytes": policy.max_total_bytes,
    }


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
        if self.max_timeout is not None:
            if (
                isinstance(self.max_timeout, bool)
                or not isinstance(self.max_timeout, (int, float))
                or not math.isfinite(float(self.max_timeout))
                or float(self.max_timeout) <= 0.0
            ):
                raise ValueError("max_timeout must be finite and positive")
            object.__setattr__(self, "max_timeout", float(self.max_timeout))
        capabilities = frozenset(
            ShellCapability(capability)
            for capability in self.required_capabilities
        ) | {ShellCapability.EXECUTE}
        effects = frozenset(
            CommandEffect(effect)
            for effect in self.effects
        )
        object.__setattr__(
            self,
            "risk",
            CommandRisk(self.risk),
        )
        object.__setattr__(self, "required_capabilities", capabilities)
        object.__setattr__(self, "effects", effects)
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
            "arguments": _argument_policy_dict(self.arguments),
            "environment": _environment_policy_dict(self.environment),
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
