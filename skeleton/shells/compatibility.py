"""Compatibility checks across shell-plane policy, command, and runtime versions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.shells.commands import CommandCatalog
from skeleton.shells.runner import ShellPolicy


@dataclass(frozen=True)
class ShellCompatibilityRequirement:
    min_schema_version: int = 1
    max_schema_version: int = 1
    required_commands: frozenset[str] = frozenset()
    required_environment_keys: frozenset[str] = frozenset()
    require_no_inherited_environment: bool = False

    def __post_init__(self) -> None:
        if self.min_schema_version <= 0 or self.max_schema_version < self.min_schema_version:
            raise ValueError("invalid compatibility schema range")
        object.__setattr__(self, "required_commands", frozenset(self.required_commands))
        object.__setattr__(self, "required_environment_keys", frozenset(self.required_environment_keys))


@dataclass(frozen=True)
class ShellCompatibilityResult:
    compatible: bool
    reasons: tuple[str, ...]
    schema_version: int

    def to_dict(self) -> dict[str, object]:
        return {
            "compatible": self.compatible,
            "reasons": list(self.reasons),
            "schema_version": self.schema_version,
        }


class ShellCompatibility:
    def check(
        self,
        policy: ShellPolicy,
        catalog: CommandCatalog,
        requirement: ShellCompatibilityRequirement | None = None,
        *,
        schema_version: int = 1,
    ) -> ShellCompatibilityResult:
        requirement = requirement or ShellCompatibilityRequirement()
        reasons: list[str] = []

        if not requirement.min_schema_version <= schema_version <= requirement.max_schema_version:
            reasons.append("shell schema version outside required range")

        command_names = set(catalog.names())
        missing_commands = requirement.required_commands - command_names
        if missing_commands:
            reasons.append("required commands are missing from catalog")

        missing_env = requirement.required_environment_keys - set(policy.allowed_env)
        if missing_env:
            reasons.append("required environment keys are not allowed by policy")

        if requirement.require_no_inherited_environment and policy.inherited_env:
            reasons.append("inherited environment is not permitted")

        return ShellCompatibilityResult(not reasons, tuple(reasons), schema_version)
