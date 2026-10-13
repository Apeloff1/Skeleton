"""Composition and inheritance for era/room definitions (STU-ERAS slice 2).

Raw era mappings may carry an ``extends`` key naming a base era, and raw room
mappings may carry an ``extends`` key naming a room template. Composition runs
on plain dicts *before* schema validation, strips every ``extends`` key, and
hands the merged result to :class:`EraSpec` so the canonical schema stays the
single fail-closed gate. Pure and deterministic; inputs are never mutated.

Merge rules (child wins):
- scalars: child value replaces base value;
- ``tags``: ordered union, base first, duplicates dropped;
- ``exits``: merged by ``direction``; a child exit replaces the base exit;
- era ``rooms``: merged by ``id``; matching rooms merge, new rooms append.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from skeleton.simulation.era.scripting.schema import EraSpec, SchemaError

MAX_DEPTH = 8
EXTENDS = "extends"


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError("bad-type", path, f"expected object, got {type(value).__name__}")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise SchemaError("bad-type", path, f"expected list, got {type(value).__name__}")
    return list(value)


def _union_tags(base: Any, over: Any, path: str) -> list[Any]:
    out: list[Any] = []
    for tag in _list(base, path) + _list(over, path):
        if tag not in out:
            out.append(tag)
    return out


def _merge_keyed(base: Any, over: Any, key: str, path: str, merge) -> list[Any]:
    merged: list[Any] = [copy.deepcopy(x) for x in _list(base, path)]
    for i, item in enumerate(_list(over, path)):
        item = _mapping(item, f"{path}[{i}]")
        ident = item.get(key)
        slot = next(
            (j for j, m in enumerate(merged) if isinstance(m, dict) and m.get(key) == ident),
            None,
        )
        if slot is None or ident is None:
            merged.append(copy.deepcopy(item))
        else:
            merged[slot] = merge(merged[slot], item, f"{path}[{i}]")
    return merged


def _replace(base: dict[str, Any], over: dict[str, Any], path: str) -> dict[str, Any]:
    return copy.deepcopy(over)


def merge_room(base: Mapping[str, Any], over: Mapping[str, Any], path: str = "room") -> dict[str, Any]:
    """Merge two raw room mappings; ``over`` wins. ``extends`` keys are dropped."""
    base = _mapping(dict(base), path)
    over = _mapping(dict(over), path)
    out = {k: copy.deepcopy(v) for k, v in base.items() if k != EXTENDS}
    for k, v in over.items():
        if k == EXTENDS:
            continue
        if k == "tags":
            out["tags"] = _union_tags(base.get("tags"), v, f"{path}.tags")
        elif k == "exits":
            out["exits"] = _merge_keyed(base.get("exits"), v, "direction", f"{path}.exits", _replace)
        else:
            out[k] = copy.deepcopy(v)
    return out


def resolve_room(
    room: Mapping[str, Any],
    templates: Mapping[str, Mapping[str, Any]],
    path: str = "room",
) -> dict[str, Any]:
    """Resolve a room's ``extends`` chain against ``templates``."""
    chain: list[Mapping[str, Any]] = [_mapping(dict(room), path)]
    seen: list[str] = []
    cur: Mapping[str, Any] = room
    while EXTENDS in cur:
        name = cur[EXTENDS]
        if not isinstance(name, str):
            raise SchemaError("bad-extends", f"{path}.extends", "expected template name")
        if name in seen:
            raise SchemaError("extends-cycle", f"{path}.extends", " -> ".join(seen + [name]))
        if len(seen) >= MAX_DEPTH:
            raise SchemaError("extends-too-deep", f"{path}.extends", f"max {MAX_DEPTH}")
        if name not in templates:
            raise SchemaError("unknown-template", f"{path}.extends", name)
        seen.append(name)
        cur = _mapping(dict(templates[name]), f"templates.{name}")
        chain.append(cur)
    out: dict[str, Any] = {}
    for layer in reversed(chain):
        out = merge_room(out, layer, path)
    return out


def merge_era(base: Mapping[str, Any], over: Mapping[str, Any], path: str = "era") -> dict[str, Any]:
    """Merge two raw era mappings; ``over`` wins. ``extends`` keys are dropped."""
    base = _mapping(dict(base), path)
    over = _mapping(dict(over), path)
    out = {k: copy.deepcopy(v) for k, v in base.items() if k != EXTENDS}
    for k, v in over.items():
        if k == EXTENDS:
            continue
        if k == "tags":
            out["tags"] = _union_tags(base.get("tags"), v, f"{path}.tags")
        elif k == "rooms":
            out["rooms"] = _merge_keyed(base.get("rooms"), v, "id", f"{path}.rooms", merge_room)
        else:
            out[k] = copy.deepcopy(v)
    return out


def compose_era(
    data: Mapping[str, Any],
    bases: Mapping[str, Mapping[str, Any]] | None = None,
    templates: Mapping[str, Mapping[str, Any]] | None = None,
    path: str = "era",
) -> dict[str, Any]:
    """Return a fully composed raw era dict (no ``extends`` keys anywhere)."""
    bases = bases or {}
    templates = templates or {}
    chain: list[Mapping[str, Any]] = [_mapping(dict(data), path)]
    seen: list[str] = []
    cur: Mapping[str, Any] = data
    while EXTENDS in cur:
        name = cur[EXTENDS]
        if not isinstance(name, str):
            raise SchemaError("bad-extends", f"{path}.extends", "expected base era id")
        if name in seen:
            raise SchemaError("extends-cycle", f"{path}.extends", " -> ".join(seen + [name]))
        if len(seen) >= MAX_DEPTH:
            raise SchemaError("extends-too-deep", f"{path}.extends", f"max {MAX_DEPTH}")
        if name not in bases:
            raise SchemaError("unknown-base", f"{path}.extends", name)
        seen.append(name)
        cur = _mapping(dict(bases[name]), f"bases.{name}")
        chain.append(cur)
    out: dict[str, Any] = {}
    for layer in reversed(chain):
        out = merge_era(out, layer, path)
    rooms = _list(out.get("rooms"), f"{path}.rooms")
    if rooms:
        out["rooms"] = [
            resolve_room(_mapping(r, f"{path}.rooms[{i}]"), templates, f"{path}.rooms[{i}]")
            for i, r in enumerate(rooms)
        ]
    return out


def load_composed(
    data: Mapping[str, Any],
    bases: Mapping[str, Mapping[str, Any]] | None = None,
    templates: Mapping[str, Mapping[str, Any]] | None = None,
) -> EraSpec:
    """Compose then validate through the canonical schema."""
    return EraSpec.from_dict(compose_era(data, bases, templates))
