"""Environment construction and validation for child processes."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.errors import EnvironmentRejected, ShellErrorCode, ShellErrorContext

_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class EnvironmentValueRule:
    pattern: str | None = None
    choices: frozenset[str] = frozenset()
    max_bytes: int = 4096
    allow_empty: bool = True

    def __post_init__(self) -> None:
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if self.pattern is not None:
            re.compile(self.pattern)
        object.__setattr__(self, "choices", frozenset(self.choices))

    def accepts(self, value: str) -> bool:
        if not self.allow_empty and not value:
            return False
        if "\x00" in value:
            return False
        if len(value.encode("utf-8")) > self.max_bytes:
            return False
        if self.choices and value not in self.choices:
            return False
        if self.pattern is not None and re.fullmatch(self.pattern, value) is None:
            return False
        return True


@dataclass(frozen=True)
class EnvironmentPolicy:
    """Complete child-environment policy.

    Keys not present in ``rules`` are rejected.  Parent inheritance is opt-in per
    key and also requires the key to exist in ``rules``.
    """

    rules: Mapping[str, EnvironmentValueRule] = field(default_factory=dict)
    inherited: frozenset[str] = frozenset()
    required: frozenset[str] = frozenset()
    fixed: Mapping[str, str] = field(default_factory=dict)
    max_total_bytes: int = 32_768

    def __post_init__(self) -> None:
        rules = dict(self.rules)
        fixed = dict(self.fixed)
        inherited = frozenset(self.inherited)
        required = frozenset(self.required)
        if self.max_total_bytes <= 0:
            raise ValueError("max_total_bytes must be positive")
        for key in set(rules) | set(fixed) | inherited | required:
            if not _KEY.fullmatch(key):
                raise ValueError(f"invalid environment key: {key!r}")
        if not inherited <= set(rules):
            raise ValueError("inherited keys must have value rules")
        if not required <= set(rules):
            raise ValueError("required keys must have value rules")
        for key, value in fixed.items():
            rule = rules.get(key)
            if rule is None:
                raise ValueError("fixed keys must have value rules")
            if not rule.accepts(value):
                raise ValueError(f"fixed value for {key!r} violates its rule")
        object.__setattr__(self, "rules", MappingProxyType(rules))
        object.__setattr__(self, "fixed", MappingProxyType(fixed))
        object.__setattr__(self, "inherited", inherited)
        object.__setattr__(self, "required", required)

    @classmethod
    def empty(cls) -> "EnvironmentPolicy":
        return cls()

    def _reject(self, command: str, detail: str) -> None:
        raise EnvironmentRejected(
            ShellErrorContext(ShellErrorCode.ENVIRONMENT, command=command, detail=detail)
        )

    def build(
        self,
        command: str,
        requested: Mapping[str, str] | None = None,
        *,
        parent: Mapping[str, str] | None = None,
    ) -> Mapping[str, str]:
        source = os.environ if parent is None else parent
        result = dict(self.fixed)
        for key in self.inherited:
            if key in source:
                result[key] = source[key]
        for key, value in (requested or {}).items():
            rule = self.rules.get(key)
            if rule is None:
                self._reject(command, f"environment key {key!r} is not allowed")
            if not isinstance(value, str) or not rule.accepts(value):
                self._reject(command, f"environment value for {key!r} is rejected")
            result[key] = value
        missing = sorted(key for key in self.required if key not in result)
        if missing:
            self._reject(command, "missing required environment keys: " + ", ".join(missing))
        for key, value in result.items():
            rule = self.rules[key]
            if not rule.accepts(value):
                self._reject(command, f"environment value for {key!r} is rejected")
        total = sum(len(key.encode("utf-8")) + len(value.encode("utf-8")) + 2 for key, value in result.items())
        if total > self.max_total_bytes:
            self._reject(command, "child environment exceeds byte limit")
        return MappingProxyType(result)

    def allowed_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self.rules))
