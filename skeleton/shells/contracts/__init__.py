"""Typed command contracts for the policy-bound shell plane."""

from skeleton.shells.contracts.catalog import CatalogStatistics, catalog_statistics, standard_catalog, standard_contracts
from skeleton.shells.contracts.core import (
    CommandContract,
    CommandContractCatalog,
    ContractBoundExecutor,
    ContractDecision,
    ContractExecutionPolicy,
    ContractViolation,
    FlagSpec,
    RiskTier,
    ToolEffect,
    VerbContract,
)
from skeleton.shells.contracts.intent import CommandIntent, CommandIntentStep, CommandPlan, ContractPlanner, PlannedStep
from skeleton.shells.contracts.profiles import (
    POLICY_FACTORIES,
    build_policy,
    developer_policy,
    infrastructure_review_policy,
    package_review_policy,
    read_only_policy,
    release_policy,
    vcs_maintainer_policy,
)

__all__ = [
    "CatalogStatistics",
    "catalog_statistics",
    "standard_catalog",
    "standard_contracts",
    "CommandContract",
    "CommandContractCatalog",
    "ContractBoundExecutor",
    "ContractDecision",
    "ContractExecutionPolicy",
    "ContractViolation",
    "FlagSpec",
    "RiskTier",
    "ToolEffect",
    "VerbContract",
    "CommandIntent",
    "CommandIntentStep",
    "CommandPlan",
    "ContractPlanner",
    "PlannedStep",
    "POLICY_FACTORIES",
    "build_policy",
    "developer_policy",
    "infrastructure_review_policy",
    "package_review_policy",
    "read_only_policy",
    "release_policy",
    "vcs_maintainer_policy",
]
