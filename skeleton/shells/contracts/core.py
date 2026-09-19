"""Typed command contracts layered over the existing ShellExecutor.

Contracts describe command verbs, flags, positional bounds, effects, and risk.
They do not resolve executables and never execute processes themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

from skeleton.shells.executor import ExecutionOutcome, ShellExecutor
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.runner import ShellCommand
from skeleton.shells.session import ShellSession


class ToolEffect(str, Enum):
    READ = "read"
    WRITE = "write"
    NETWORK = "network"
    PROCESS = "process"
    PACKAGE = "package"
    BUILD = "build"
    TEST = "test"
    VCS = "vcs"
    ARCHIVE = "archive"
    DESTRUCTIVE = "destructive"
    PRIVILEGED = "privileged"


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_RISK_ORDER = {
    RiskTier.LOW: 0,
    RiskTier.MEDIUM: 1,
    RiskTier.HIGH: 2,
    RiskTier.CRITICAL: 3,
}


@dataclass(frozen=True)
class FlagSpec:
    token: str
    takes_value: bool = False
    repeatable: bool = False
    choices: frozenset[str] = frozenset()
    value_pattern: str | None = None
    max_value_length: int = 4096
    effects: frozenset[ToolEffect] = frozenset()

    def __post_init__(self) -> None:
        if not self.token.startswith("-") or self.token in {"-", "--"}:
            raise ValueError("flag token must be a concrete option")
        if "=" in self.token:
            raise ValueError("flag token may not contain equals")
        if isinstance(self.max_value_length, bool) or self.max_value_length <= 0:
            raise ValueError("max_value_length must be positive")
        if self.value_pattern is not None:
            re.compile(self.value_pattern)
        object.__setattr__(self, "choices", frozenset(self.choices))
        object.__setattr__(self, "effects", frozenset(self.effects))

    def validate_value(self, value: str) -> bool:
        if len(value) > self.max_value_length or "\x00" in value:
            return False
        if self.choices and value not in self.choices:
            return False
        if self.value_pattern is not None and re.fullmatch(self.value_pattern, value) is None:
            return False
        return True

    def to_dict(self) -> dict[str, object]:
        return {
            "token": self.token,
            "takes_value": self.takes_value,
            "repeatable": self.repeatable,
            "choices": sorted(self.choices),
            "value_pattern": self.value_pattern,
            "max_value_length": self.max_value_length,
            "effects": sorted(effect.value for effect in self.effects),
        }


@dataclass(frozen=True)
class VerbContract:
    name: str
    effects: frozenset[ToolEffect]
    risk: RiskTier = RiskTier.LOW
    flags: Mapping[str, FlagSpec] = field(default_factory=dict)
    min_positionals: int = 0
    max_positionals: int | None = None
    positional_pattern: str = r"[^\x00]{1,4096}"
    deny_patterns: tuple[str, ...] = ()
    allow_double_dash: bool = True
    requires_approval: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name or self.name.startswith("-") or "\x00" in self.name:
            raise ValueError("invalid verb name")
        if self.min_positionals < 0:
            raise ValueError("min_positionals must be non-negative")
        if self.max_positionals is not None and self.max_positionals < self.min_positionals:
            raise ValueError("max_positionals cannot be below minimum")
        re.compile(self.positional_pattern)
        for pattern in self.deny_patterns:
            re.compile(pattern)
        normalized = dict(self.flags)
        for name, spec in normalized.items():
            if name != spec.token:
                raise ValueError("flag mapping key must equal token")
        object.__setattr__(self, "effects", frozenset(self.effects))
        object.__setattr__(self, "flags", MappingProxyType(normalized))
        object.__setattr__(self, "deny_patterns", tuple(self.deny_patterns))

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "effects": sorted(effect.value for effect in self.effects),
            "risk": self.risk.value,
            "flags": {name: spec.to_dict() for name, spec in sorted(self.flags.items())},
            "min_positionals": self.min_positionals,
            "max_positionals": self.max_positionals,
            "positional_pattern": self.positional_pattern,
            "deny_patterns": list(self.deny_patterns),
            "allow_double_dash": self.allow_double_dash,
            "requires_approval": self.requires_approval,
            "description": self.description,
        }


@dataclass(frozen=True)
class ContractDecision:
    allowed: bool
    command: str
    verb: str
    effects: frozenset[ToolEffect]
    risk: RiskTier
    reason: str
    normalized_args: tuple[str, ...]
    requires_approval: bool = False

    def require(self) -> None:
        if not self.allowed:
            raise ContractViolation(self.reason)


class ContractViolation(ValueError):
    pass


@dataclass(frozen=True)
class CommandContract:
    logical_name: str
    description: str
    verbs: Mapping[str, VerbContract]
    aliases: frozenset[str] = frozenset()
    max_args: int = 256
    max_arg_bytes: int = 131_072
    default_verb: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.+-]+", self.logical_name):
            raise ValueError("invalid logical command name")
        normalized = dict(self.verbs)
        if not normalized:
            raise ValueError("command contract requires at least one verb")
        for name, verb in normalized.items():
            if name != verb.name:
                raise ValueError("verb mapping key must equal verb name")
        if self.default_verb is not None and self.default_verb not in normalized:
            raise ValueError("default_verb must name a registered verb")
        if isinstance(self.max_args, bool) or self.max_args <= 0:
            raise ValueError("max_args must be positive")
        if isinstance(self.max_arg_bytes, bool) or self.max_arg_bytes <= 0:
            raise ValueError("max_arg_bytes must be positive")
        object.__setattr__(self, "verbs", MappingProxyType(normalized))
        object.__setattr__(self, "aliases", frozenset(self.aliases))

    def _reject(self, verb: str, reason: str, args: Sequence[str]) -> ContractDecision:
        return ContractDecision(
            False,
            self.logical_name,
            verb,
            frozenset(),
            RiskTier.CRITICAL,
            reason,
            tuple(args),
            False,
        )

    def validate(self, args: Sequence[str]) -> ContractDecision:
        values = tuple(args)
        if len(values) > self.max_args:
            return self._reject("", "argument count exceeds command contract", values)
        total = 0
        for value in values:
            if not isinstance(value, str):
                return self._reject("", "all command arguments must be strings", values)
            if "\x00" in value:
                return self._reject("", "argument contains NUL", values)
            total += len(value.encode("utf-8"))
        if total > self.max_arg_bytes:
            return self._reject("", "argument bytes exceed command contract", values)

        if values and values[0] in self.verbs:
            verb_name = values[0]
            tail = values[1:]
        elif self.default_verb is not None:
            verb_name = self.default_verb
            tail = values
        else:
            supplied = values[0] if values else ""
            return self._reject(supplied, "unknown or missing command verb", values)

        verb = self.verbs[verb_name]
        positionals: list[str] = []
        effects = set(verb.effects)
        seen_flags: set[str] = set()
        option_mode = True
        i = 0
        while i < len(tail):
            token = tail[i]
            for denied in verb.deny_patterns:
                if re.search(denied, token):
                    return self._reject(verb_name, "argument matched denied verb pattern", values)
            if option_mode and token == "--":
                if not verb.allow_double_dash:
                    return self._reject(verb_name, "double dash is not allowed", values)
                option_mode = False
                i += 1
                continue
            if option_mode and token.startswith("-") and token != "-":
                name = token
                inline_value: str | None = None
                if "=" in token:
                    name, inline_value = token.split("=", 1)
                spec = verb.flags.get(name)
                if spec is None:
                    return self._reject(verb_name, f"flag {name!r} is not allowed", values)
                if name in seen_flags and not spec.repeatable:
                    return self._reject(verb_name, f"flag {name!r} may not repeat", values)
                seen_flags.add(name)
                effects.update(spec.effects)
                if spec.takes_value:
                    if inline_value is None:
                        i += 1
                        if i >= len(tail):
                            return self._reject(verb_name, f"flag {name!r} requires value", values)
                        inline_value = tail[i]
                    if not spec.validate_value(inline_value):
                        return self._reject(verb_name, f"value for {name!r} is rejected", values)
                elif inline_value is not None:
                    return self._reject(verb_name, f"flag {name!r} does not accept value", values)
                i += 1
                continue
            positionals.append(token)
            i += 1

        if len(positionals) < verb.min_positionals:
            return self._reject(verb_name, "too few positional arguments", values)
        if verb.max_positionals is not None and len(positionals) > verb.max_positionals:
            return self._reject(verb_name, "too many positional arguments", values)
        for positional in positionals:
            if re.fullmatch(verb.positional_pattern, positional) is None:
                return self._reject(verb_name, "positional argument rejected by contract", values)

        return ContractDecision(
            True,
            self.logical_name,
            verb_name,
            frozenset(effects),
            verb.risk,
            "allowed",
            values,
            verb.requires_approval,
        )

    def require(self, args: Sequence[str]) -> ContractDecision:
        decision = self.validate(args)
        decision.require()
        return decision

    def build(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        stdin: bytes | None = None,
        timeout: float | None = None,
    ) -> ShellCommand:
        decision = self.require(args)
        return ShellCommand(
            self.logical_name,
            decision.normalized_args,
            cwd=cwd,
            env=dict(env or {}),
            stdin=stdin,
            timeout=timeout,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "logical_name": self.logical_name,
            "description": self.description,
            "aliases": sorted(self.aliases),
            "default_verb": self.default_verb,
            "max_args": self.max_args,
            "max_arg_bytes": self.max_arg_bytes,
            "verbs": {name: verb.to_dict() for name, verb in sorted(self.verbs.items())},
        }


class CommandContractCatalog:
    def __init__(self, contracts: Iterable[CommandContract] = ()) -> None:
        self._contracts: dict[str, CommandContract] = {}
        self._aliases: dict[str, str] = {}
        for contract in contracts:
            self.register(contract)

    def register(self, contract: CommandContract, *, replace: bool = False) -> None:
        if contract.logical_name in self._contracts and not replace:
            raise ValueError(f"command contract already registered: {contract.logical_name}")
        if replace and contract.logical_name in self._contracts:
            old = self._contracts[contract.logical_name]
            for alias in old.aliases:
                if self._aliases.get(alias) == old.logical_name:
                    self._aliases.pop(alias, None)
        for alias in contract.aliases:
            existing = self._aliases.get(alias)
            if existing is not None and existing != contract.logical_name:
                raise ValueError(f"command alias collision: {alias}")
            self._aliases[alias] = contract.logical_name
        self._contracts[contract.logical_name] = contract

    def resolve(self, name: str) -> CommandContract:
        canonical = self._aliases.get(name, name)
        try:
            return self._contracts[canonical]
        except KeyError as exc:
            raise KeyError(f"unknown command contract: {name}") from exc

    def validate(self, name: str, args: Sequence[str]) -> ContractDecision:
        return self.resolve(name).validate(args)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._contracts))

    def by_effect(self, effect: ToolEffect) -> tuple[CommandContract, ...]:
        result = []
        for contract in self._contracts.values():
            if any(effect in verb.effects for verb in contract.verbs.values()):
                result.append(contract)
        return tuple(sorted(result, key=lambda item: item.logical_name))

    def to_dict(self) -> dict[str, object]:
        return {
            name: self._contracts[name].to_dict()
            for name in sorted(self._contracts)
        }


@dataclass(frozen=True)
class ContractExecutionPolicy:
    max_risk: RiskTier = RiskTier.MEDIUM
    allowed_effects: frozenset[ToolEffect] = frozenset(ToolEffect)
    require_approval_for: frozenset[ToolEffect] = frozenset(
        {ToolEffect.NETWORK, ToolEffect.DESTRUCTIVE, ToolEffect.PRIVILEGED}
    )

    def inspect(self, decision: ContractDecision, *, approved: bool = False) -> ContractDecision:
        if not decision.allowed:
            return decision
        if _RISK_ORDER[decision.risk] > _RISK_ORDER[self.max_risk]:
            return ContractDecision(
                False,
                decision.command,
                decision.verb,
                decision.effects,
                decision.risk,
                "contract risk exceeds execution policy",
                decision.normalized_args,
                decision.requires_approval,
            )
        forbidden = decision.effects - self.allowed_effects
        if forbidden:
            return ContractDecision(
                False,
                decision.command,
                decision.verb,
                decision.effects,
                decision.risk,
                "contract effect is not allowed by execution policy",
                decision.normalized_args,
                decision.requires_approval,
            )
        needs_approval = decision.requires_approval or bool(decision.effects & self.require_approval_for)
        if needs_approval and not approved:
            return ContractDecision(
                False,
                decision.command,
                decision.verb,
                decision.effects,
                decision.risk,
                "contract requires explicit approval",
                decision.normalized_args,
                True,
            )
        return decision


class ContractBoundExecutor:
    """Validate a typed contract, then delegate to the one ShellExecutor authority."""

    def __init__(
        self,
        executor: ShellExecutor,
        catalog: CommandContractCatalog,
        *,
        policy: ContractExecutionPolicy | None = None,
    ) -> None:
        self.executor = executor
        self.catalog = catalog
        self.policy = policy or ContractExecutionPolicy()

    def execute(
        self,
        command: str,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        stdin: bytes | None = None,
        timeout: float | None = None,
        retry: RetryPolicy | None = None,
        session: ShellSession | None = None,
        correlation_id: str | None = None,
        approved: bool = False,
    ) -> ExecutionOutcome:
        contract = self.catalog.resolve(command)
        decision = self.policy.inspect(contract.require(args), approved=approved)
        decision.require()
        shell_command = ShellCommand(
            contract.logical_name,
            decision.normalized_args,
            cwd=cwd,
            env=dict(env or {}),
            stdin=stdin,
            timeout=timeout,
        )
        return self.executor.execute(
            shell_command,
            retry=retry,
            session=session,
            correlation_id=correlation_id,
        )
