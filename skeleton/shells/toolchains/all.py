"""Unified discovery surface for built-in logical toolchain contracts."""

from __future__ import annotations

from skeleton.shells.toolchains import archive, artifact, build, container, data, dotnet, git, go, infrastructure, jvm, node, posix, python, quality, rust
from skeleton.shells.toolchains.catalog import ToolchainCatalog
from skeleton.shells.toolchains.types import LogicalCommandContract

_MODULES = (
    git,
    python,
    node,
    rust,
    go,
    jvm,
    dotnet,
    build,
    container,
    posix,
    infrastructure,
    data,
    artifact,
    archive,
    quality,
)


def all_contracts() -> tuple[LogicalCommandContract, ...]:
    contracts: list[LogicalCommandContract] = []
    for module in _MODULES:
        contracts.extend(module.contracts())
    contracts.sort(key=lambda contract: contract.name)
    names = [contract.name for contract in contracts]
    if len(names) != len(set(names)):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise RuntimeError("duplicate built-in logical contracts: " + ", ".join(duplicates))
    return tuple(contracts)


def default_catalog() -> ToolchainCatalog:
    return ToolchainCatalog(all_contracts())


def executable_keys() -> tuple[str, ...]:
    return tuple(sorted({contract.executable_key for contract in all_contracts()}))


def contracts_by_executable(key: str) -> tuple[LogicalCommandContract, ...]:
    return tuple(contract for contract in all_contracts() if contract.executable_key == key)


def contracts_by_tag(tag: str) -> tuple[LogicalCommandContract, ...]:
    return tuple(contract for contract in all_contracts() if tag in contract.tags)


ALL_CONTRACTS = all_contracts()
DEFAULT_CATALOG = ToolchainCatalog(ALL_CONTRACTS)
