"""Catalog and explicit absolute-path binding for logical toolchain contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from types import MappingProxyType
from typing import Iterable, Mapping

from skeleton.shells.provenance import canonical_json
from skeleton.shells.toolchains.types import BoundToolchain, LogicalCommandContract


class ToolchainBindingError(ValueError):
    pass


@dataclass(frozen=True)
class ToolchainCatalogSnapshot:
    contracts: Mapping[str, LogicalCommandContract]
    digest: str

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self.contracts))

    def by_executable_key(self, key: str) -> tuple[LogicalCommandContract, ...]:
        return tuple(
            self.contracts[name]
            for name in sorted(self.contracts)
            if self.contracts[name].executable_key == key
        )


class ToolchainCatalog:
    def __init__(self, contracts: Iterable[LogicalCommandContract] = ()) -> None:
        self._contracts: dict[str, LogicalCommandContract] = {}
        for contract in contracts:
            self.register(contract)

    def register(self, contract: LogicalCommandContract, *, replace: bool = False) -> None:
        if contract.name in self._contracts and not replace:
            raise ValueError(f"toolchain contract already registered: {contract.name}")
        self._contracts[contract.name] = contract

    def extend(self, contracts: Iterable[LogicalCommandContract]) -> None:
        for contract in contracts:
            self.register(contract)

    def get(self, name: str) -> LogicalCommandContract:
        try:
            return self._contracts[name]
        except KeyError as exc:
            raise KeyError(f"unknown toolchain contract: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._contracts))

    def snapshot(self) -> ToolchainCatalogSnapshot:
        document = [self._contracts[name].to_dict() for name in sorted(self._contracts)]
        digest = hashlib.sha256(canonical_json(document)).hexdigest()
        return ToolchainCatalogSnapshot(MappingProxyType(dict(self._contracts)), digest)

    def bind(
        self,
        executable_paths: Mapping[str, str],
        *,
        names: Iterable[str] | None = None,
        require_all: bool = True,
    ) -> BoundToolchain:
        selected = self.names() if names is None else tuple(sorted(set(names)))
        unknown = [name for name in selected if name not in self._contracts]
        if unknown:
            raise ToolchainBindingError("unknown contract names: " + ", ".join(unknown))

        definitions = []
        used_paths: dict[str, str] = {}
        missing_keys: set[str] = set()
        for name in selected:
            contract = self._contracts[name]
            path = executable_paths.get(contract.executable_key)
            if path is None:
                missing_keys.add(contract.executable_key)
                if require_all:
                    continue
                continue
            definitions.append(contract.bind(path))
            used_paths[contract.executable_key] = path

        if require_all and missing_keys:
            raise ToolchainBindingError(
                "missing absolute executable bindings: " + ", ".join(sorted(missing_keys))
            )
        return BoundToolchain(tuple(definitions), used_paths)

    def filter_tags(self, *tags: str) -> "ToolchainCatalog":
        wanted = set(tags)
        return ToolchainCatalog(
            contract
            for contract in self._contracts.values()
            if wanted <= set(contract.tags)
        )
