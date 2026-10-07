"""Composition of the standard typed command-contract catalog."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.contracts.catalog_data import contracts as data_contracts
from skeleton.shells.contracts.catalog_infrastructure import contracts as infrastructure_contracts
from skeleton.shells.contracts.catalog_javascript import contracts as javascript_contracts
from skeleton.shells.contracts.catalog_native import contracts as native_contracts
from skeleton.shells.contracts.catalog_python import contracts as python_contracts
from skeleton.shells.contracts.catalog_system import contracts as system_contracts
from skeleton.shells.contracts.catalog_vcs import contracts as vcs_contracts
from skeleton.shells.contracts.core import CommandContract, CommandContractCatalog, RiskTier, ToolEffect


@dataclass(frozen=True)
class CatalogStatistics:
    commands: int
    verbs: int
    flags: int
    approval_verbs: int
    low_risk: int
    medium_risk: int
    high_risk: int
    critical_risk: int
    read_commands: int
    write_commands: int
    network_commands: int
    destructive_commands: int


def standard_contracts() -> tuple[CommandContract, ...]:
    values = (
        *vcs_contracts(),
        *python_contracts(),
        *javascript_contracts(),
        *native_contracts(),
        *system_contracts(),
        *data_contracts(),
        *infrastructure_contracts(),
    )
    names = [contract.logical_name for contract in values]
    if len(names) != len(set(names)):
        duplicates = sorted(name for name in set(names) if names.count(name) > 1)
        raise RuntimeError(f"duplicate standard command contracts: {duplicates}")
    return tuple(sorted(values, key=lambda contract: contract.logical_name))


def standard_catalog() -> CommandContractCatalog:
    return CommandContractCatalog(standard_contracts())


def catalog_statistics(
    contracts: tuple[CommandContract, ...] | None = None,
) -> CatalogStatistics:
    values = standard_contracts() if contracts is None else contracts
    verbs = [verb for contract in values for verb in contract.verbs.values()]
    risk_counts = {risk: 0 for risk in RiskTier}
    for verb in verbs:
        risk_counts[verb.risk] += 1

    def has_effect(contract: CommandContract, effect: ToolEffect) -> bool:
        return any(effect in verb.effects for verb in contract.verbs.values())

    return CatalogStatistics(
        commands=len(values),
        verbs=len(verbs),
        flags=sum(len(verb.flags) for verb in verbs),
        approval_verbs=sum(verb.requires_approval for verb in verbs),
        low_risk=risk_counts[RiskTier.LOW],
        medium_risk=risk_counts[RiskTier.MEDIUM],
        high_risk=risk_counts[RiskTier.HIGH],
        critical_risk=risk_counts[RiskTier.CRITICAL],
        read_commands=sum(has_effect(contract, ToolEffect.READ) for contract in values),
        write_commands=sum(has_effect(contract, ToolEffect.WRITE) for contract in values),
        network_commands=sum(has_effect(contract, ToolEffect.NETWORK) for contract in values),
        destructive_commands=sum(has_effect(contract, ToolEffect.DESTRUCTIVE) for contract in values),
    )
