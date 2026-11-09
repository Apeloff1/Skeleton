"""Typed add/remove/change ops over GamePlan paths.

A path is a tuple of segments. Into a list of objects carrying ``id`` a
string segment selects by id; otherwise an int indexes. ``add`` on a list
path appends (or inserts at ``index``); ``add`` on a mapping key creates it.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

OPS = ("add", "remove", "change")
MAX_OPS = 64


class DiffError(ValueError):
    pass


@dataclass(frozen=True)
class EditOp:
    op: str
    path: tuple
    value: Any = None
    old: Any = None
    index: int | None = None

    def __post_init__(self) -> None:
        if self.op not in OPS:
            raise DiffError(f"unknown op {self.op!r}")
        if not isinstance(self.path, tuple) or not self.path or not all(
                isinstance(s, str) or (isinstance(s, int) and not isinstance(s, bool)) for s in self.path):
            raise DiffError("path must be a non-empty tuple of str/int segments")

    def as_dict(self) -> dict[str, Any]:
        d = {"op": self.op, "path": list(self.path)}
        if self.op != "remove":
            d["value"] = self.value
        if self.op != "add":
            d["old"] = self.old
        if self.index is not None:
            d["index"] = self.index
        return d


@dataclass(frozen=True)
class PlanDiff:
    ops: tuple[EditOp, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if len(self.ops) > MAX_OPS:
            raise DiffError(f"at most {MAX_OPS} ops")

    def as_dict(self) -> dict[str, Any]:
        return {"ops": [o.as_dict() for o in self.ops]}

    @classmethod
    def from_obj(cls, obj: Any) -> "PlanDiff":
        ops = obj.get("ops") if isinstance(obj, Mapping) else obj
        if not isinstance(ops, list) or not ops:
            raise DiffError("diff needs a non-empty ops list")
        out = []
        for o in ops:
            if not isinstance(o, Mapping) or not isinstance(o.get("path"), list):
                raise DiffError("each op needs op and path")
            out.append(EditOp(o.get("op"), tuple(o["path"]), o.get("value"), o.get("old"), o.get("index")))
        return cls(tuple(out))


def _step(node: Any, seg: Any) -> tuple[Any, Any]:
    """Return (key_in_container, child) for one segment."""
    if isinstance(node, Mapping):
        if seg not in node:
            raise DiffError(f"missing key {seg!r}")
        return seg, node[seg]
    if isinstance(node, list):
        if isinstance(seg, int):
            if not -len(node) <= seg < len(node):
                raise DiffError(f"index {seg} out of range")
            return seg, node[seg]
        for i, item in enumerate(node):
            if isinstance(item, Mapping) and item.get("id") == seg:
                return i, item
        for i, item in enumerate(node):
            if item == seg:  # plain string lists (exits, systems)
                return i, item
        raise DiffError(f"no list item {seg!r}")
    raise DiffError(f"cannot descend into {type(node).__name__} at {seg!r}")


def _resolve(root: Any, path: tuple) -> tuple[Any, Any]:
    node = root
    for seg in path[:-1]:
        _, node = _step(node, seg)
    return node, path[-1]


def apply_diff(plan: Mapping[str, Any], diff: PlanDiff) -> tuple[dict[str, Any], PlanDiff]:
    """Apply to a deep copy. Returns ``(new_plan, applied)`` where ``applied``
    records ``old`` values and concrete indexes, so it can be inverted."""
    new = copy.deepcopy(dict(plan))
    applied = []
    for op in diff.ops:
        if op.op == "add":
            target = _step(*_resolve(new, op.path))[1]
            if isinstance(target, list):
                at = len(target) if op.index is None else op.index
                if not 0 <= at <= len(target):
                    raise DiffError(f"insert index {at} out of range")
                if isinstance(op.value, Mapping) and op.value.get("id") in {
                        x.get("id") for x in target if isinstance(x, Mapping)}:
                    raise DiffError(f"duplicate id {op.value.get('id')!r}")
                target.insert(at, copy.deepcopy(op.value))
                applied.append(EditOp("add", op.path, op.value, index=at))
            else:
                raise DiffError("add targets a list; use change for keys")
        elif op.op == "remove":
            parent, last = _resolve(new, op.path)
            key, old = _step(parent, last)
            del parent[key]
            idx = key if isinstance(parent, list) else None
            applied.append(EditOp("remove", op.path[:-1] + (idx,) if idx is not None else op.path, old=old, index=idx))
        else:
            parent, last = _resolve(new, op.path)
            if isinstance(parent, Mapping) and last not in parent:
                parent[last] = copy.deepcopy(op.value)  # new key
                applied.append(EditOp("change", op.path, op.value, old=None, index=-1))
                continue
            key, old = _step(parent, last)
            parent[key] = copy.deepcopy(op.value)
            applied.append(EditOp("change", op.path, op.value, old=old))
    return new, PlanDiff(tuple(applied))


def invert(applied: PlanDiff) -> PlanDiff:
    """Inverse of an *applied* diff (as returned by :func:`apply_diff`)."""
    out = []
    for op in reversed(applied.ops):
        if op.op == "add":
            out.append(EditOp("remove", op.path + (op.index,)))
        elif op.op == "remove":
            if op.index is None:  # removed a mapping key
                out.append(EditOp("change", op.path, op.old, index=-1))
            else:
                out.append(EditOp("add", op.path[:-1], op.old, index=op.index))
        elif op.index == -1:  # created key -> drop it
            out.append(EditOp("remove", op.path))
        else:
            out.append(EditOp("change", op.path, op.old, old=op.value))
    return PlanDiff(tuple(out))
