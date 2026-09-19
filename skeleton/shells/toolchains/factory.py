"""Factories for explicit logical toolchain command contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.shells.arguments import ArgumentPolicy, OptionRule, ValueConstraint
from skeleton.shells.capabilities import ShellCapability
from skeleton.shells.environment import EnvironmentPolicy, EnvironmentValueRule
from skeleton.shells.toolchains.constraints import (
    GIT_REF,
    HEX_SHA,
    IDENTIFIER,
    INTEGER,
    PACKAGE_SPEC,
    PYTHON_MODULE,
    RELATIVE_PATH,
    SAFE_TOKEN,
    SHORT_TOKEN,
    TEST_SELECTOR,
    URL_HTTPS,
)
from skeleton.shells.toolchains.types import CommandEffect, CommandRisk, LogicalCommandContract


_CONSTRAINTS = {
    "safe": SAFE_TOKEN,
    "short": SHORT_TOKEN,
    "identifier": IDENTIFIER,
    "path": RELATIVE_PATH,
    "module": PYTHON_MODULE,
    "package": PACKAGE_SPEC,
    "test": TEST_SELECTOR,
    "git_ref": GIT_REF,
    "sha": HEX_SHA,
    "integer": INTEGER,
    "https": URL_HTTPS,
}


@dataclass(frozen=True)
class OptionSpec:
    name: str
    value: str | None = None
    repeatable: bool = False


@dataclass(frozen=True)
class OperationSpec:
    logical_name: str
    executable_key: str
    subcommand: str | None = None
    fixed_prefix: tuple[str, ...] = ()
    options: tuple[OptionSpec, ...] = ()
    positionals: tuple[str, ...] = ()
    variadic: str | None = None
    min_positionals: int | None = None
    max_positionals: int | None = None
    effects: frozenset[CommandEffect] = frozenset({CommandEffect.READ})
    risk: CommandRisk = CommandRisk.LOW
    timeout: float | None = 60.0
    allow_stdin: bool = False
    allow_nonzero_success: bool = False
    capabilities: frozenset[ShellCapability] = frozenset({ShellCapability.EXECUTE})
    tags: frozenset[str] = frozenset()
    description: str = ""
    env_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.logical_name or not self.executable_key:
            raise ValueError("logical_name and executable_key are required")
        if self.subcommand and self.fixed_prefix:
            raise ValueError("choose subcommand or fixed_prefix, not both")
        for kind in self.positionals:
            constraint(kind)
        if self.variadic is not None:
            constraint(self.variadic)
        for option in self.options:
            if option.value is not None:
                constraint(option.value)


def constraint(name: str) -> ValueConstraint:
    try:
        return _CONSTRAINTS[name]
    except KeyError as exc:
        raise ValueError(f"unknown toolchain constraint: {name}") from exc


def _option(spec: OptionSpec) -> OptionRule:
    return OptionRule(
        name=spec.name,
        takes_value=spec.value is not None,
        repeatable=spec.repeatable,
        value=ValueConstraint() if spec.value is None else constraint(spec.value),
    )


def _argument_policy(spec: OperationSpec) -> ArgumentPolicy:
    positional: list[ValueConstraint] = []
    option_rules = {item.name: _option(item) for item in spec.options}
    consumed_positionals = 0
    prefix_positionals = 0

    # ArgumentPolicy treats every dash-prefixed token as an option. Model
    # literal CLI prefixes accordingly instead of pretending "-m", "--build",
    # "--version", and similar tokens are positional argv values.
    if spec.subcommand is not None:
        if spec.subcommand.startswith("-"):
            option_rules.setdefault(spec.subcommand, OptionRule(spec.subcommand))
        else:
            positional.append(
                ValueConstraint(
                    choices=frozenset({spec.subcommand}),
                    min_length=1,
                    max_length=len(spec.subcommand),
                )
            )
            prefix_positionals += 1

    fixed = list(spec.fixed_prefix)
    index = 0
    while index < len(fixed):
        token = fixed[index]
        if token.startswith("-"):
            if token == "-m":
                if index + 1 < len(fixed) and not fixed[index + 1].startswith("-"):
                    literal = fixed[index + 1]
                    option_rules.setdefault(
                        token,
                        OptionRule(
                            token,
                            takes_value=True,
                            value=ValueConstraint(
                                choices=frozenset({literal}),
                                min_length=1,
                                max_length=len(literal),
                            ),
                        ),
                    )
                    index += 2
                    continue
                if spec.positionals:
                    option_rules.setdefault(
                        token,
                        OptionRule(
                            token,
                            takes_value=True,
                            value=constraint(spec.positionals[0]),
                        ),
                    )
                    consumed_positionals = 1
                    index += 1
                    continue
            option_rules.setdefault(token, OptionRule(token))
        else:
            positional.append(
                ValueConstraint(
                    choices=frozenset({token}),
                    min_length=1,
                    max_length=len(token),
                )
            )
            prefix_positionals += 1
        index += 1

    positional.extend(
        constraint(kind)
        for kind in spec.positionals[consumed_positionals:]
    )
    if spec.min_positionals is None:
        minimum = prefix_positionals + len(spec.positionals) - consumed_positionals
    else:
        declared_prefix = (1 if spec.subcommand is not None else 0) + len(spec.fixed_prefix)
        nonpositional_prefix = declared_prefix - prefix_positionals
        minimum = max(
            0,
            spec.min_positionals - nonpositional_prefix - consumed_positionals,
        )
    maximum = spec.max_positionals
    if maximum is not None and spec.min_positionals is not None:
        declared_prefix = (1 if spec.subcommand is not None else 0) + len(spec.fixed_prefix)
        nonpositional_prefix = declared_prefix - prefix_positionals
        maximum = max(
            0,
            maximum - nonpositional_prefix - consumed_positionals,
        )
    variadic = None if spec.variadic is None else constraint(spec.variadic)
    if maximum is None and variadic is None:
        maximum = len(positional)
    return ArgumentPolicy(
        options=option_rules,
        positional=tuple(positional),
        variadic=variadic,
        min_positionals=minimum,
        max_positionals=maximum,
        allow_double_dash=True,
        allow_option_equals=True,
        deny_tokens=frozenset(),
        deny_patterns=(),
        max_total_args=256,
        max_total_bytes=131_072,
        allow_unknown_options=False,
    )


def _environment(spec: OperationSpec) -> EnvironmentPolicy:
    return EnvironmentPolicy(
        rules={key: EnvironmentValueRule(max_bytes=4096) for key in spec.env_keys}
    )


def build_contract(spec: OperationSpec) -> LogicalCommandContract:
    capabilities = set(spec.capabilities)
    if spec.allow_stdin:
        capabilities.add(ShellCapability.STDIN)
    if spec.allow_nonzero_success:
        capabilities.add(ShellCapability.NONZERO_SUCCESS)
    if spec.env_keys:
        capabilities.add(ShellCapability.CUSTOM_ENV)
    return LogicalCommandContract(
        name=spec.logical_name,
        executable_key=spec.executable_key,
        arguments=_argument_policy(spec),
        environment=_environment(spec),
        required_capabilities=frozenset(capabilities),
        max_timeout=spec.timeout,
        allow_stdin=spec.allow_stdin,
        allow_nonzero_success=spec.allow_nonzero_success,
        description=spec.description,
        effects=spec.effects,
        risk=spec.risk,
        tags=spec.tags,
    )


def build_many(specs: Iterable[OperationSpec]) -> tuple[LogicalCommandContract, ...]:
    contracts = tuple(build_contract(spec) for spec in specs)
    names = [contract.name for contract in contracts]
    if len(names) != len(set(names)):
        raise ValueError("duplicate logical command contract names")
    return contracts
