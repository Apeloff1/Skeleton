"""Executable registry for policy-bound shell execution."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Iterable, Mapping

from skeleton.shells.capabilities import ShellCapability

_NAME = re.compile(r"^[A-Za-z0-9_.+-]+$")
_TAG = re.compile(r"^[A-Za-z0-9_.:/+-]+$")


@dataclass(frozen=True)
class ExecutableSpec:
    """Canonical metadata for one executable authority grant."""

    name: str
    path: str
    capabilities: frozenset[ShellCapability] = frozenset({ShellCapability.EXECUTE})
    tags: frozenset[str] = frozenset()
    description: str = ""

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name):
            raise ValueError("invalid executable name")
        candidate = Path(self.path).expanduser()
        if not candidate.is_absolute():
            raise ValueError("executable path must be absolute")
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError("executable does not exist") from exc
        if not resolved.is_file():
            raise ValueError("executable must resolve to a file")
        for tag in self.tags:
            if not _TAG.fullmatch(tag):
                raise ValueError(f"invalid executable tag: {tag!r}")
        object.__setattr__(self, "path", str(resolved))
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))
        object.__setattr__(self, "tags", frozenset(self.tags))

    def to_dict(self, *, include_path: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "capabilities": sorted(cap.value for cap in self.capabilities),
            "tags": sorted(self.tags),
            "description": self.description,
        }
        if include_path:
            payload["path"] = self.path
        return payload


@dataclass(frozen=True)
class RegistrySnapshot:
    specs: Mapping[str, ExecutableSpec]
    aliases: Mapping[str, str]
    digest: str

    def resolve(self, name: str) -> ExecutableSpec:
        canonical = self.aliases.get(name, name)
        try:
            return self.specs[canonical]
        except KeyError as exc:
            raise KeyError(f"unregistered executable: {name!r}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self.specs))

    def to_policy_mapping(self) -> Mapping[str, str]:
        return MappingProxyType({name: spec.path for name, spec in self.specs.items()})


class ExecutableRegistry:
    """Mutable builder that freezes into a deterministic registry snapshot."""

    def __init__(self) -> None:
        self._specs: dict[str, ExecutableSpec] = {}
        self._aliases: dict[str, str] = {}
        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def _ensure_mutable(self) -> None:
        if self._frozen:
            raise RuntimeError("executable registry is frozen")

    def register(self, spec: ExecutableSpec, *, replace: bool = False) -> None:
        self._ensure_mutable()
        if spec.name in self._aliases:
            raise ValueError("executable name conflicts with alias")
        if spec.name in self._specs and not replace:
            raise ValueError(f"executable already registered: {spec.name}")
        self._specs[spec.name] = spec

    def register_path(
        self,
        name: str,
        path: str,
        *,
        capabilities: Iterable[ShellCapability] = (ShellCapability.EXECUTE,),
        tags: Iterable[str] = (),
        description: str = "",
        replace: bool = False,
    ) -> ExecutableSpec:
        spec = ExecutableSpec(
            name=name,
            path=path,
            capabilities=frozenset(capabilities),
            tags=frozenset(tags),
            description=description,
        )
        self.register(spec, replace=replace)
        return spec

    def alias(self, alias: str, canonical: str) -> None:
        self._ensure_mutable()
        if not _NAME.fullmatch(alias):
            raise ValueError("invalid executable alias")
        if alias in self._specs:
            raise ValueError("alias conflicts with executable name")
        if canonical not in self._specs:
            raise KeyError(f"unknown canonical executable: {canonical!r}")
        if alias == canonical:
            raise ValueError("alias may not point to itself")
        self._aliases[alias] = canonical

    def remove(self, name: str) -> None:
        self._ensure_mutable()
        if name not in self._specs:
            raise KeyError(name)
        del self._specs[name]
        stale = [alias for alias, canonical in self._aliases.items() if canonical == name]
        for alias in stale:
            del self._aliases[alias]

    def resolve(self, name: str) -> ExecutableSpec:
        canonical = self._aliases.get(name, name)
        try:
            return self._specs[canonical]
        except KeyError as exc:
            raise KeyError(f"unregistered executable: {name!r}") from exc

    def by_tag(self, tag: str) -> tuple[ExecutableSpec, ...]:
        return tuple(sorted((spec for spec in self._specs.values() if tag in spec.tags), key=lambda spec: spec.name))

    def snapshot(self) -> RegistrySnapshot:
        document = {
            "executables": [self._specs[name].to_dict() for name in sorted(self._specs)],
            "aliases": {name: self._aliases[name] for name in sorted(self._aliases)},
        }
        encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        return RegistrySnapshot(
            MappingProxyType(dict(self._specs)),
            MappingProxyType(dict(self._aliases)),
            digest,
        )

    def freeze(self) -> RegistrySnapshot:
        self._frozen = True
        return self.snapshot()

    @classmethod
    def from_specs(cls, specs: Iterable[ExecutableSpec]) -> "ExecutableRegistry":
        registry = cls()
        for spec in specs:
            registry.register(spec)
        return registry
