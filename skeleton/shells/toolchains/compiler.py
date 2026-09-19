"""Compile portable logical contracts into an executable shell authority boundary.

Compilation is explicit: callers provide absolute executable paths and workspace
roots. The compiler creates one logical executable mapping per contract, a
per-command argv policy set, a per-command environment policy router, and a
capability grant that is sufficient for the selected contracts but no broader
than necessary for runner-level enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence

from skeleton.shells.arguments import ArgumentPolicySet
from skeleton.shells.capabilities import CapabilityGrant, ShellCapability
from skeleton.shells.environment import EnvironmentPolicy
from skeleton.shells.executor import ExecutorConfig, ShellExecutor
from skeleton.shells.receipts import ReceiptChain
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.toolchains.catalog import ToolchainCatalog
from skeleton.shells.toolchains.types import CommandRisk, LogicalCommandContract

if TYPE_CHECKING:
    from skeleton.shells.toolchains.profiles import ContractProfile


_RISK_ORDER = {
    CommandRisk.LOW: 0,
    CommandRisk.MODERATE: 1,
    CommandRisk.HIGH: 2,
}


class ToolchainCompileError(ValueError):
    pass


class CommandEnvironmentPolicySet:
    """Default-deny command-to-environment-policy router.

    ShellExecutor only requires a build(command, requested) method. Routing
    here preserves each contract's narrow environment authority instead of
    widening all selected contracts to the union of environment keys.
    """

    def __init__(self, policies: Mapping[str, EnvironmentPolicy]) -> None:
        self._policies = MappingProxyType(dict(policies))

    def build(
        self,
        command: str,
        requested: Mapping[str, str] | None = None,
        *,
        parent: Mapping[str, str] | None = None,
    ) -> Mapping[str, str]:
        try:
            policy = self._policies[command]
        except KeyError as exc:
            raise ToolchainCompileError(
                f"no environment policy is compiled for {command!r}"
            ) from exc
        return policy.build(command, requested, parent=parent)

    def get(self, command: str) -> EnvironmentPolicy:
        try:
            return self._policies[command]
        except KeyError as exc:
            raise KeyError(f"unknown compiled command: {command}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._policies))

    def allowed_keys(self, command: str) -> tuple[str, ...]:
        return self.get(command).allowed_keys()

    def union_allowed_keys(self) -> frozenset[str]:
        keys: set[str] = set()
        for policy in self._policies.values():
            keys.update(policy.allowed_keys())
        return frozenset(keys)


@dataclass(frozen=True)
class ToolchainCompilerLimits:
    default_timeout: float = 30.0
    absolute_max_timeout: float = 3600.0
    max_output_bytes: int = 8 * 1024 * 1024
    max_input_bytes: int = 8 * 1024 * 1024
    max_env_bytes: int = 64 * 1024
    max_args: int = 256
    max_arg_bytes: int = 131_072
    large_output_threshold_bytes: int = 1024 * 1024
    long_running_threshold_seconds: float = 30.0

    def __post_init__(self) -> None:
        numeric = (
            ("default_timeout", self.default_timeout),
            ("absolute_max_timeout", self.absolute_max_timeout),
            ("long_running_threshold_seconds", self.long_running_threshold_seconds),
        )
        for name, value in numeric:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.default_timeout > self.absolute_max_timeout:
            raise ValueError("default timeout cannot exceed absolute maximum")
        for name in (
            "max_output_bytes",
            "max_input_bytes",
            "max_env_bytes",
            "max_args",
            "max_arg_bytes",
            "large_output_threshold_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class ToolchainAuthorityPolicy:
    """Compile-time authority filter independent of runtime argv validation."""

    max_risk: CommandRisk = CommandRisk.MODERATE
    allow_effects: frozenset[str] = frozenset()
    deny_effects: frozenset[str] = frozenset()
    required_tags: frozenset[str] = frozenset()
    denied_tags: frozenset[str] = frozenset()
    denied_names: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_risk", CommandRisk(self.max_risk))
        object.__setattr__(
            self,
            "allow_effects",
            frozenset(
                value.value if hasattr(value, "value") else str(value)
                for value in self.allow_effects
            ),
        )
        object.__setattr__(
            self,
            "deny_effects",
            frozenset(
                value.value if hasattr(value, "value") else str(value)
                for value in self.deny_effects
            ),
        )
        object.__setattr__(self, "required_tags", frozenset(self.required_tags))
        object.__setattr__(self, "denied_tags", frozenset(self.denied_tags))
        object.__setattr__(self, "denied_names", frozenset(self.denied_names))

    def accepts(self, contract: LogicalCommandContract) -> bool:
        if contract.name in self.denied_names:
            return False
        if _RISK_ORDER[contract.risk] > _RISK_ORDER[self.max_risk]:
            return False
        effects = frozenset(effect.value for effect in contract.effects)
        if self.allow_effects and not effects <= self.allow_effects:
            return False
        if effects & self.deny_effects:
            return False
        if not self.required_tags <= contract.tags:
            return False
        if contract.tags & self.denied_tags:
            return False
        return True

    def require(self, contract: LogicalCommandContract) -> None:
        if not self.accepts(contract):
            raise ToolchainCompileError(
                f"contract is outside compile authority: {contract.name}"
            )


@dataclass(frozen=True)
class CompiledToolchain:
    contracts: Mapping[str, LogicalCommandContract]
    executor: ShellExecutor
    arguments: ArgumentPolicySet
    environments: CommandEnvironmentPolicySet
    roots: tuple[Path, ...]
    executable_bindings: Mapping[str, str]
    compiler_limits: ToolchainCompilerLimits

    def __post_init__(self) -> None:
        object.__setattr__(self, "contracts", MappingProxyType(dict(self.contracts)))
        object.__setattr__(
            self,
            "executable_bindings",
            MappingProxyType(dict(self.executable_bindings)),
        )
        object.__setattr__(self, "roots", tuple(self.roots))

    def get(self, name: str) -> LogicalCommandContract:
        try:
            return self.contracts[name]
        except KeyError as exc:
            raise KeyError(f"uncompiled logical command: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self.contracts))

    def runner_policy(self) -> ShellPolicy:
        return self.executor.runner.policy

    def grant(self) -> CapabilityGrant:
        return self.executor.grant


def _normalize_roots(roots: Sequence[Path | str]) -> tuple[Path, ...]:
    normalized: list[Path] = []
    for root in roots:
        candidate = Path(root).expanduser().resolve(strict=True)
        if not candidate.is_dir():
            raise ToolchainCompileError("toolchain root must be a directory")
        normalized.append(candidate)
    if not normalized:
        raise ToolchainCompileError("at least one workspace root is required")
    return tuple(dict.fromkeys(normalized))


def _select_contracts(
    catalog: ToolchainCatalog,
    *,
    names: Iterable[str] | None,
    profile: ContractProfile | None,
    authority: ToolchainAuthorityPolicy | None,
) -> tuple[LogicalCommandContract, ...]:
    if names is None:
        selected = tuple(catalog.get(name) for name in catalog.names())
    else:
        selected = tuple(catalog.get(name) for name in sorted(set(names)))
    if profile is not None:
        selected = profile.select(selected)
    if authority is not None:
        selected = tuple(
            contract for contract in selected if authority.accepts(contract)
        )
    if not selected:
        raise ToolchainCompileError("contract selection is empty")
    return tuple(sorted(selected, key=lambda contract: contract.name))


def compile_toolchain(
    catalog: ToolchainCatalog,
    *,
    executable_paths: Mapping[str, str],
    cwd_roots: Sequence[Path | str],
    names: Iterable[str] | None = None,
    profile: ContractProfile | None = None,
    authority: ToolchainAuthorityPolicy | None = None,
    limits: ToolchainCompilerLimits | None = None,
    receipt_chain: ReceiptChain | None = None,
) -> CompiledToolchain:
    """Compile a contract selection into a ready policy-bound executor."""

    compiler_limits = limits or ToolchainCompilerLimits()
    roots = _normalize_roots(cwd_roots)
    contracts = _select_contracts(
        catalog,
        names=names,
        profile=profile,
        authority=authority,
    )

    logical_executables: dict[str, str] = {}
    bindings: dict[str, str] = {}
    argument_policies = ArgumentPolicySet()
    environment_policies: dict[str, EnvironmentPolicy] = {}
    allowed_env: set[str] = set()
    capabilities: set[ShellCapability] = {ShellCapability.EXECUTE}
    max_contract_timeout = compiler_limits.default_timeout

    for contract in contracts:
        if authority is not None:
            authority.require(contract)
        try:
            executable = executable_paths[contract.executable_key]
        except KeyError as exc:
            raise ToolchainCompileError(
                f"missing executable binding for {contract.executable_key!r}"
            ) from exc
        logical_executables[contract.name] = executable
        bindings[contract.executable_key] = executable
        argument_policies.register(contract.name, contract.arguments)
        environment_policies[contract.name] = contract.environment
        allowed_env.update(contract.environment.allowed_keys())
        capabilities.update(contract.required_capabilities)
        if contract.environment.allowed_keys():
            capabilities.add(ShellCapability.CUSTOM_ENV)
        if contract.allow_stdin:
            capabilities.add(ShellCapability.STDIN)
        if contract.allow_nonzero_success:
            capabilities.add(ShellCapability.NONZERO_SUCCESS)
        if contract.max_timeout is not None:
            max_contract_timeout = max(max_contract_timeout, contract.max_timeout)
            if contract.max_timeout > compiler_limits.long_running_threshold_seconds:
                capabilities.add(ShellCapability.LONG_RUNNING)

    if max_contract_timeout > compiler_limits.absolute_max_timeout:
        raise ToolchainCompileError(
            "selected contract timeout exceeds compiler absolute maximum"
        )
    max_timeout = max_contract_timeout
    if compiler_limits.max_output_bytes > compiler_limits.large_output_threshold_bytes:
        capabilities.add(ShellCapability.LARGE_OUTPUT)

    environments = CommandEnvironmentPolicySet(environment_policies)
    runner_policy = ShellPolicy(
        executables=logical_executables,
        cwd_roots=roots,
        allowed_env=frozenset(allowed_env),
        inherited_env=frozenset(),
        default_timeout=min(compiler_limits.default_timeout, max_timeout),
        max_timeout=max_timeout,
        max_output_bytes=compiler_limits.max_output_bytes,
        max_input_bytes=compiler_limits.max_input_bytes,
        max_env_bytes=compiler_limits.max_env_bytes,
        max_args=compiler_limits.max_args,
        max_arg_bytes=compiler_limits.max_arg_bytes,
    )
    grant = CapabilityGrant(
        frozenset(capabilities),
        principal="toolchain-compiler",
        scope="shell.toolchain",
    )
    executor = ShellExecutor(
        ShellRunner(runner_policy),
        grant=grant,
        arguments=argument_policies,
        environment=environments,
        receipts=receipt_chain,
        config=ExecutorConfig(
            long_running_threshold_seconds=compiler_limits.long_running_threshold_seconds,
            large_output_threshold_bytes=compiler_limits.large_output_threshold_bytes,
        ),
    )
    return CompiledToolchain(
        contracts={contract.name: contract for contract in contracts},
        executor=executor,
        arguments=argument_policies,
        environments=environments,
        roots=roots,
        executable_bindings=bindings,
        compiler_limits=compiler_limits,
    )
