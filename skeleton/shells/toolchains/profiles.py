"""Capability views over the built-in logical command catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.shells.toolchains.all import ALL_CONTRACTS
from skeleton.shells.toolchains.types import CommandEffect, CommandRisk, LogicalCommandContract

_RISK_ORDER = {
    CommandRisk.LOW: 0,
    CommandRisk.MODERATE: 1,
    CommandRisk.HIGH: 2,
}


@dataclass(frozen=True)
class ContractProfile:
    name: str
    max_risk: CommandRisk = CommandRisk.LOW
    include_effects: frozenset[CommandEffect] = frozenset()
    exclude_effects: frozenset[CommandEffect] = frozenset()
    required_tags: frozenset[str] = frozenset()
    excluded_tags: frozenset[str] = frozenset()
    explicit_names: frozenset[str] = frozenset()

    def accepts(self, contract: LogicalCommandContract) -> bool:
        if _RISK_ORDER[contract.risk] > _RISK_ORDER[self.max_risk]:
            return False
        if self.include_effects and not (self.include_effects & contract.effects):
            return False
        if self.exclude_effects & contract.effects:
            return False
        if not self.required_tags <= contract.tags:
            return False
        if self.excluded_tags & contract.tags:
            return False
        if self.explicit_names and contract.name not in self.explicit_names:
            return False
        return True

    def select(
        self,
        contracts: Iterable[LogicalCommandContract] = ALL_CONTRACTS,
    ) -> tuple[LogicalCommandContract, ...]:
        return tuple(sorted(
            (contract for contract in contracts if self.accepts(contract)),
            key=lambda contract: contract.name,
        ))


READ_ONLY = ContractProfile(
    "read-only",
    max_risk=CommandRisk.LOW,
    exclude_effects=frozenset({
        CommandEffect.WRITE,
        CommandEffect.PROCESS,
        CommandEffect.NETWORK,
    }),
)

CI_VERIFY = ContractProfile(
    "ci-verify",
    max_risk=CommandRisk.MODERATE,
    include_effects=frozenset({
        CommandEffect.TEST,
        CommandEffect.LINT,
        CommandEffect.FORMAT,
        CommandEffect.BUILD,
    }),
    exclude_effects=frozenset({
        CommandEffect.NETWORK,
    }),
)

NETWORK_READ = ContractProfile(
    "network-read",
    max_risk=CommandRisk.MODERATE,
    include_effects=frozenset({CommandEffect.NETWORK}),
    exclude_effects=frozenset({CommandEffect.PROCESS}),
)

SOURCE_CONTROL_READ = ContractProfile(
    "source-control-read",
    max_risk=CommandRisk.LOW,
    required_tags=frozenset({"git"}),
    exclude_effects=frozenset({CommandEffect.WRITE, CommandEffect.NETWORK}),
)

SOURCE_CONTROL_WRITE = ContractProfile(
    "source-control-write",
    max_risk=CommandRisk.HIGH,
    required_tags=frozenset({"git"}),
    include_effects=frozenset({CommandEffect.WRITE}),
)

CONTAINER_OBSERVE = ContractProfile(
    "container-observe",
    max_risk=CommandRisk.LOW,
    required_tags=frozenset({"container"}),
    exclude_effects=frozenset({
        CommandEffect.WRITE,
        CommandEffect.PROCESS,
        CommandEffect.NETWORK,
    }),
)

FILESYSTEM_OBSERVE = ContractProfile(
    "filesystem-observe",
    max_risk=CommandRisk.LOW,
    required_tags=frozenset({"posix"}),
    exclude_effects=frozenset({CommandEffect.WRITE, CommandEffect.PROCESS}),
)

FORMAT_CHECK = ContractProfile(
    "format-check",
    max_risk=CommandRisk.LOW,
    include_effects=frozenset({CommandEffect.FORMAT}),
    exclude_effects=frozenset({CommandEffect.WRITE}),
)

FORMAT_WRITE = ContractProfile(
    "format-write",
    max_risk=CommandRisk.MODERATE,
    include_effects=frozenset({CommandEffect.FORMAT, CommandEffect.WRITE}),
)

TEST_ONLY = ContractProfile(
    "test-only",
    max_risk=CommandRisk.MODERATE,
    include_effects=frozenset({CommandEffect.TEST}),
    exclude_effects=frozenset({CommandEffect.NETWORK}),
)

LINT_ONLY = ContractProfile(
    "lint-only",
    max_risk=CommandRisk.MODERATE,
    include_effects=frozenset({CommandEffect.LINT}),
)

BUILD_LOCAL = ContractProfile(
    "build-local",
    max_risk=CommandRisk.MODERATE,
    include_effects=frozenset({CommandEffect.BUILD}),
    exclude_effects=frozenset({CommandEffect.NETWORK}),
)

PACKAGE_INSPECT = ContractProfile(
    "package-inspect",
    max_risk=CommandRisk.LOW,
    include_effects=frozenset({CommandEffect.PACKAGE}),
    exclude_effects=frozenset({CommandEffect.WRITE, CommandEffect.NETWORK}),
)

PROFILES = {
    profile.name: profile
    for profile in (
        READ_ONLY,
        CI_VERIFY,
        NETWORK_READ,
        SOURCE_CONTROL_READ,
        SOURCE_CONTROL_WRITE,
        CONTAINER_OBSERVE,
        FILESYSTEM_OBSERVE,
        FORMAT_CHECK,
        FORMAT_WRITE,
        TEST_ONLY,
        LINT_ONLY,
        BUILD_LOCAL,
        PACKAGE_INSPECT,
    )
}


def profile(name: str) -> ContractProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise KeyError(f"unknown logical command profile: {name}") from exc
