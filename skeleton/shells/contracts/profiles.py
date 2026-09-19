"""Execution-policy profiles for typed command contracts."""

from __future__ import annotations

from skeleton.shells.contracts.core import ContractExecutionPolicy, RiskTier, ToolEffect


def read_only_policy() -> ContractExecutionPolicy:
    return ContractExecutionPolicy(
        max_risk=RiskTier.MEDIUM,
        allowed_effects=frozenset(
            {
                ToolEffect.READ,
                ToolEffect.TEST,
                ToolEffect.VCS,
                ToolEffect.BUILD,
            }
        ),
        require_approval_for=frozenset(),
    )


def developer_policy() -> ContractExecutionPolicy:
    return ContractExecutionPolicy(
        max_risk=RiskTier.MEDIUM,
        allowed_effects=frozenset(
            {
                ToolEffect.READ,
                ToolEffect.WRITE,
                ToolEffect.PROCESS,
                ToolEffect.BUILD,
                ToolEffect.TEST,
                ToolEffect.VCS,
                ToolEffect.ARCHIVE,
            }
        ),
        require_approval_for=frozenset(),
    )


def package_review_policy() -> ContractExecutionPolicy:
    return ContractExecutionPolicy(
        max_risk=RiskTier.HIGH,
        allowed_effects=frozenset(
            {
                ToolEffect.READ,
                ToolEffect.WRITE,
                ToolEffect.PROCESS,
                ToolEffect.PACKAGE,
                ToolEffect.NETWORK,
                ToolEffect.TEST,
                ToolEffect.BUILD,
            }
        ),
        require_approval_for=frozenset(
            {
                ToolEffect.NETWORK,
                ToolEffect.PACKAGE,
            }
        ),
    )


def vcs_maintainer_policy() -> ContractExecutionPolicy:
    return ContractExecutionPolicy(
        max_risk=RiskTier.HIGH,
        allowed_effects=frozenset(
            {
                ToolEffect.READ,
                ToolEffect.WRITE,
                ToolEffect.NETWORK,
                ToolEffect.VCS,
                ToolEffect.PROCESS,
            }
        ),
        require_approval_for=frozenset(
            {
                ToolEffect.NETWORK,
            }
        ),
    )


def infrastructure_review_policy() -> ContractExecutionPolicy:
    return ContractExecutionPolicy(
        max_risk=RiskTier.CRITICAL,
        allowed_effects=frozenset(ToolEffect),
        require_approval_for=frozenset(
            {
                ToolEffect.NETWORK,
                ToolEffect.PRIVILEGED,
                ToolEffect.DESTRUCTIVE,
                ToolEffect.WRITE,
            }
        ),
    )


def release_policy() -> ContractExecutionPolicy:
    return ContractExecutionPolicy(
        max_risk=RiskTier.HIGH,
        allowed_effects=frozenset(
            {
                ToolEffect.READ,
                ToolEffect.WRITE,
                ToolEffect.NETWORK,
                ToolEffect.PACKAGE,
                ToolEffect.BUILD,
                ToolEffect.TEST,
                ToolEffect.VCS,
                ToolEffect.ARCHIVE,
                ToolEffect.PROCESS,
            }
        ),
        require_approval_for=frozenset(
            {
                ToolEffect.NETWORK,
                ToolEffect.PACKAGE,
            }
        ),
    )


POLICY_FACTORIES = {
    "read_only": read_only_policy,
    "developer": developer_policy,
    "package_review": package_review_policy,
    "vcs_maintainer": vcs_maintainer_policy,
    "infrastructure_review": infrastructure_review_policy,
    "release": release_policy,
}


def build_policy(name: str) -> ContractExecutionPolicy:
    try:
        return POLICY_FACTORIES[name]()
    except KeyError as exc:
        raise KeyError(f"unknown command-contract execution profile: {name}") from exc
