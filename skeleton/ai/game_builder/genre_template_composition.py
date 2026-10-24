"""Genre template composition (#807 B030).

Reusable mechanic packs compose into vertical slices without copy-paste forks:
packs are immutable, referenced by id + digest, and a slice is a resolved,
conflict-checked composition. B021 (mechanics core) and B027 (combat) are not
on main yet; packs are therefore declarative descriptors that those runtimes
(and B028's quest runtime) can bind to later.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

SCHEMA_ID = "gameplay.genre_composition.v1"


class CompositionError(ValueError):
    """Invalid pack or composition (fail closed)."""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class MechanicPack:
    pack_id: str
    provides: tuple[str, ...]
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    params: tuple[tuple[str, Any], ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "MechanicPack":
        unknown = set(data) - {"id", "provides", "requires", "conflicts", "params"}
        if unknown:
            raise CompositionError(f"unknown pack keys: {sorted(unknown)}")
        pid = data.get("id")
        if not isinstance(pid, str) or not pid:
            raise CompositionError("pack id required")
        provides = tuple(sorted(data.get("provides", ())))
        if not provides:
            raise CompositionError(f"{pid}: pack must provide at least one capability")
        params = data.get("params", {})
        if not isinstance(params, Mapping):
            raise CompositionError(f"{pid}: params must be an object")
        return cls(pid, provides, tuple(sorted(data.get("requires", ()))),
                   tuple(sorted(data.get("conflicts", ()))), tuple(sorted(params.items())))

    def to_mapping(self) -> dict[str, Any]:
        return {"id": self.pack_id, "provides": list(self.provides), "requires": list(self.requires),
                "conflicts": list(self.conflicts), "params": dict(self.params)}

    @property
    def digest(self) -> str:
        return _digest(self.to_mapping())


class PackRegistry:
    def __init__(self, packs: Sequence[MechanicPack | Mapping[str, Any]] = ()) -> None:
        self._packs: dict[str, MechanicPack] = {}
        for pack in packs:
            self.register(pack)

    def register(self, pack: MechanicPack | Mapping[str, Any]) -> MechanicPack:
        p = pack if isinstance(pack, MechanicPack) else MechanicPack.from_mapping(pack)
        existing = self._packs.get(p.pack_id)
        if existing is not None and existing != p:
            raise CompositionError(f"{p.pack_id}: pack ids are immutable; publish a new id instead of forking")
        self._packs[p.pack_id] = p
        return p

    def get(self, pack_id: str) -> MechanicPack:
        try:
            return self._packs[pack_id]
        except KeyError:
            raise CompositionError(f"unknown pack {pack_id}") from None


def compose_slice(
    registry: PackRegistry,
    slice_id: str,
    pack_ids: Sequence[str],
    *,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve packs into a vertical slice; requirements must be met, no conflicts, no dup capability."""
    if not slice_id:
        raise CompositionError("slice id required")
    if len(set(pack_ids)) != len(pack_ids):
        raise CompositionError("duplicate pack in slice")
    packs = [registry.get(pid) for pid in pack_ids]
    providers: dict[str, str] = {}
    for p in packs:
        for cap in p.provides:
            if cap in providers:
                raise CompositionError(f"capability {cap} provided by both {providers[cap]} and {p.pack_id}")
            providers[cap] = p.pack_id
    for p in packs:
        missing = [r for r in p.requires if r not in providers]
        if missing:
            raise CompositionError(f"{p.pack_id}: unmet requirements {missing}")
        clash = [c for c in p.conflicts if c in providers or c in pack_ids]
        if clash:
            raise CompositionError(f"{p.pack_id}: conflicts with {clash}")
    overrides = dict(overrides or {})
    unknown = set(overrides) - set(pack_ids)
    if unknown:
        raise CompositionError(f"overrides for packs not in slice: {sorted(unknown)}")
    resolved = []
    for p in sorted(packs, key=lambda x: x.pack_id):
        params = dict(p.params)
        bad = set(overrides.get(p.pack_id, {})) - set(params)
        if bad:
            raise CompositionError(f"{p.pack_id}: overrides for undeclared params {sorted(bad)}")
        params.update(overrides.get(p.pack_id, {}))
        resolved.append({"id": p.pack_id, "digest": p.digest, "params": params})
    body = {"schema": SCHEMA_ID, "slice_id": slice_id, "packs": resolved,
            "capabilities": dict(sorted(providers.items()))}
    return {**body, "digest": _digest(body)}


def verify_slice(registry: PackRegistry, slice_doc: Mapping[str, Any]) -> bool:
    """True only if digests match and every referenced pack is unchanged in the registry."""
    if slice_doc.get("schema") != SCHEMA_ID:
        return False
    body = {k: v for k, v in slice_doc.items() if k != "digest"}
    if slice_doc.get("digest") != _digest(body):
        return False
    try:
        return all(registry.get(p["id"]).digest == p["digest"] for p in slice_doc.get("packs", ()))
    except (CompositionError, KeyError, TypeError):
        return False


__all__ = ["SCHEMA_ID", "CompositionError", "MechanicPack", "PackRegistry", "compose_slice", "verify_slice"]
