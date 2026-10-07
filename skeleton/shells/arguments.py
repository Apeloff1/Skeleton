"""Argument validation policies for registered executables.

The process runner guarantees argv semantics, but argv-only execution is not by
itself an authorization policy.  This module lets command owners constrain
which flags, positional shapes, and values may reach a particular executable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from types import MappingProxyType
from typing import Mapping, Pattern, Sequence

from skeleton.shells.errors import ArgumentRejected, ShellErrorCode, ShellErrorContext


@dataclass(frozen=True)
class ValueConstraint:
    pattern: str | None = None
    choices: frozenset[str] = frozenset()
    min_length: int = 0
    max_length: int = 4096

    def __post_init__(self) -> None:
        if self.min_length < 0 or self.max_length < self.min_length:
            raise ValueError("invalid value length bounds")
        if self.pattern is not None:
            re.compile(self.pattern)
        object.__setattr__(self, "choices", frozenset(self.choices))

    def accepts(self, value: str) -> bool:
        if not self.min_length <= len(value) <= self.max_length:
            return False
        if self.choices and value not in self.choices:
            return False
        if self.pattern is not None and re.fullmatch(self.pattern, value) is None:
            return False
        return True


@dataclass(frozen=True)
class OptionRule:
    name: str
    takes_value: bool = False
    repeatable: bool = False
    value: ValueConstraint = field(default_factory=ValueConstraint)

    def __post_init__(self) -> None:
        if not self.name.startswith("-") or self.name in {"-", "--"}:
            raise ValueError("option names must be concrete dash-prefixed tokens")
        if "=" in self.name:
            raise ValueError("option name may not contain '='")


@dataclass(frozen=True)
class ArgumentPolicy:
    """Declarative argv grammar for a single logical command."""

    options: Mapping[str, OptionRule] = field(default_factory=dict)
    positional: tuple[ValueConstraint, ...] = ()
    variadic: ValueConstraint | None = None
    min_positionals: int = 0
    max_positionals: int | None = None
    allow_double_dash: bool = True
    allow_option_equals: bool = True
    deny_tokens: frozenset[str] = frozenset()
    deny_patterns: tuple[str, ...] = ()
    max_total_args: int = 128
    max_total_bytes: int = 65_536
    allow_unknown_options: bool = False

    def __post_init__(self) -> None:
        normalized = dict(self.options)
        for name, rule in normalized.items():
            if name != rule.name:
                raise ValueError("option mapping key must equal rule name")
        if self.min_positionals < 0:
            raise ValueError("min_positionals must be non-negative")
        inferred_max = len(self.positional) if self.variadic is None else None
        maximum = self.max_positionals if self.max_positionals is not None else inferred_max
        if maximum is not None and maximum < self.min_positionals:
            raise ValueError("max_positionals cannot be below min_positionals")
        if self.max_total_args <= 0 or self.max_total_bytes <= 0:
            raise ValueError("argument policy limits must be positive")
        for pattern in self.deny_patterns:
            re.compile(pattern)
        object.__setattr__(self, "options", MappingProxyType(normalized))
        object.__setattr__(self, "positional", tuple(self.positional))
        object.__setattr__(self, "deny_tokens", frozenset(self.deny_tokens))
        object.__setattr__(self, "deny_patterns", tuple(self.deny_patterns))
        object.__setattr__(self, "max_positionals", maximum)

    @classmethod
    def allow_any(cls, *, max_total_args: int = 128, max_total_bytes: int = 65_536) -> "ArgumentPolicy":
        return cls(
            variadic=ValueConstraint(max_length=max_total_bytes),
            max_positionals=None,
            max_total_args=max_total_args,
            max_total_bytes=max_total_bytes,
            allow_unknown_options=True,
        )

    def _reject(self, command: str, detail: str) -> None:
        raise ArgumentRejected(ShellErrorContext(ShellErrorCode.ARGUMENT, command=command, detail=detail))

    def _check_global_token(self, command: str, token: str) -> None:
        if "\x00" in token:
            self._reject(command, "argument contains NUL")
        if token in self.deny_tokens:
            self._reject(command, "argument token is denied")
        for pattern in self.deny_patterns:
            if re.search(pattern, token):
                self._reject(command, "argument matched denied pattern")

    def validate(self, command: str, args: Sequence[str]) -> tuple[str, ...]:
        values = tuple(args)
        if len(values) > self.max_total_args:
            self._reject(command, "argument count exceeds policy")
        total_bytes = 0
        for token in values:
            if not isinstance(token, str):
                self._reject(command, "all arguments must be strings")
            total_bytes += len(token.encode("utf-8"))
            self._check_global_token(command, token)
        if total_bytes > self.max_total_bytes:
            self._reject(command, "argument bytes exceed policy")

        positional_values: list[str] = []
        seen_options: set[str] = set()
        option_mode = True
        i = 0
        while i < len(values):
            token = values[i]
            if option_mode and token == "--":
                if not self.allow_double_dash:
                    self._reject(command, "double-dash separator is not allowed")
                option_mode = False
                i += 1
                continue
            if option_mode and token.startswith("-") and token != "-":
                # A command grammar may have an explicit literal dash-prefixed
                # token in its positional prefix (for example python -m or a
                # standalone --version contract). Only a concrete choices
                # allowlist may claim such a token; pattern-based or
                # unconstrained positionals must never turn unknown options
                # into positional data.
                positional_index = len(positional_values)
                if positional_index < len(self.positional):
                    literal = self.positional[positional_index]
                    if literal.choices and token in literal.choices:
                        positional_values.append(token)
                        i += 1
                        continue

                option_name = token
                inline_value: str | None = None
                if "=" in token:
                    if not self.allow_option_equals:
                        self._reject(command, "option=value syntax is not allowed")
                    option_name, inline_value = token.split("=", 1)
                rule = self.options.get(option_name)
                if rule is None:
                    if self.allow_unknown_options:
                        positional_values.append(token)
                        i += 1
                        continue
                    self._reject(
                        command,
                        f"option {option_name!r} is not allowed",
                    )
                if option_name in seen_options and not rule.repeatable:
                    self._reject(command, f"option {option_name!r} may not repeat")
                seen_options.add(option_name)
                if rule.takes_value:
                    if inline_value is not None:
                        value = inline_value
                    else:
                        i += 1
                        if i >= len(values):
                            self._reject(command, f"option {option_name!r} requires a value")
                        value = values[i]
                        self._check_global_token(command, value)
                    if not rule.value.accepts(value):
                        self._reject(command, f"value for {option_name!r} is rejected")
                elif inline_value is not None:
                    self._reject(command, f"option {option_name!r} does not take a value")
                i += 1
                continue
            positional_values.append(token)
            i += 1

        count = len(positional_values)
        if count < self.min_positionals:
            self._reject(command, "too few positional arguments")
        if self.max_positionals is not None and count > self.max_positionals:
            self._reject(command, "too many positional arguments")
        for index, value in enumerate(positional_values):
            constraint = self.positional[index] if index < len(self.positional) else self.variadic
            if constraint is None:
                self._reject(command, "unexpected positional argument")
            if not constraint.accepts(value):
                self._reject(command, f"positional argument {index} is rejected")
        return values


class ArgumentPolicySet:
    """Named argument policies with an explicit default-deny stance."""

    def __init__(self, policies: Mapping[str, ArgumentPolicy] | None = None) -> None:
        self._policies = dict(policies or {})

    def register(self, command: str, policy: ArgumentPolicy, *, replace: bool = False) -> None:
        if command in self._policies and not replace:
            raise ValueError(f"argument policy already registered: {command}")
        self._policies[command] = policy

    def validate(self, command: str, args: Sequence[str]) -> tuple[str, ...]:
        try:
            policy = self._policies[command]
        except KeyError as exc:
            raise ArgumentRejected(
                ShellErrorContext(
                    ShellErrorCode.ARGUMENT,
                    command=command,
                    detail="no argument policy is registered",
                )
            ) from exc
        return policy.validate(command, args)

    def snapshot(self) -> Mapping[str, ArgumentPolicy]:
        return MappingProxyType(dict(self._policies))
