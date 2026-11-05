"""Declarative content hooks over plan data, run as B095 ``content_hook`` plugins.

A hook is data, not code: a list of ops applied to a deep copy of the plan.

  {"op": "set",    "path": "levels[id=cave].name", "value": "Crystal Cave"}   override
  {"op": "remove", "path": "items[id=old]"}                                     override
  {"op": "scale",  "path": "player.speed", "factor": 1.5, "min": 0, "max": 20}  override
  {"op": "merge",  "path": "player", "value": {"jump": 2}}                     extend (new keys only)
  {"op": "append", "path": "levels", "value": [{"id": "bonus", ...}]}          extend

Path segments are ``key``, ``[3]`` or ``[id=x]`` (matches ``id``/``key``/``slug``).
Override ops need ``override_content``; extend ops need ``add_content``. Values
must be plain JSON. No exec/eval and no callables are ever taken from a mod.
"""
from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from skeleton.gameforge.batch_b09x._helpers import ContractError
from skeleton.gameforge.batch_b09x.b095_plugin_sdk import SDK_API, Host, Manifest

from .manifest import ModError, ModManifest
from .resolve import LoadPlan, ordered_before

OVERRIDE_OPS = frozenset({"set", "remove", "scale"})
EXTEND_OPS = frozenset({"merge", "append"})
MAX_OPS = 512
MAX_VALUE_BYTES = 64_000
MAX_DEPTH = 24
_SEG = re.compile(r"([A-Za-z0-9_-]+)|\[(\d+)\]|\[id=([A-Za-z0-9_.-]+)\]")


class HookError(ModError):
    """Hook rejected (malformed op, permission, path, or override conflict)."""


@runtime_checkable
class ContentHook(Protocol):
    """B095 ``content_hook`` contract: ``apply({"plan": ...}) -> plan``. Must be pure."""

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def parse_path(path: str) -> tuple[str | int | tuple[str, str], ...]:
    if not isinstance(path, str) or not path or len(path) > 256:
        raise HookError("path must be a short string")
    out: list[Any] = []
    pos = 0
    for part in path.split("."):
        if not part:
            raise HookError(f"bad path {path!r}: empty segment")
        i = 0
        while i < len(part):
            m = _SEG.match(part, i)
            if not m:
                raise HookError(f"bad path {path!r} at {pos + i}")
            out.append(m.group(1) if m.group(1) else int(m.group(2)) if m.group(2) else ("id", m.group(3)))
            i = m.end()
        pos += len(part) + 1
    if not out or len(out) > MAX_DEPTH:
        raise HookError(f"bad path {path!r}")
    return tuple(out)


def _json_value(v: Any) -> Any:
    try:
        raw = json.dumps(v, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise HookError("hook values must be plain JSON") from exc
    if len(raw) > MAX_VALUE_BYTES:
        raise HookError("hook value too large")
    return json.loads(raw)


def _step(node: Any, seg: Any, path: str) -> Any:
    if isinstance(seg, str):
        if not isinstance(node, dict) or seg not in node:
            raise HookError(f"{path}: no key {seg!r}")
        return node[seg]
    if isinstance(seg, int):
        if not isinstance(node, list) or not 0 <= seg < len(node):
            raise HookError(f"{path}: index {seg} out of range")
        return node[seg]
    return node[_find(node, seg[1], path)]


def _find(node: Any, ident: str, path: str) -> int:
    if not isinstance(node, list):
        raise HookError(f"{path}: [id=] needs a list")
    hits = [i for i, x in enumerate(node) if isinstance(x, dict)
            and any(str(x.get(f)) == ident for f in ("id", "key", "slug") if f in x)]
    if len(hits) != 1:
        raise HookError(f"{path}: [id={ident}] matched {len(hits)} items")
    return hits[0]


def _canonical(plan: Any, segs: tuple) -> str:
    """Stable key for conflict detection (``[id=x]`` and index forms normalise)."""
    out, node = [], plan
    for seg in segs:
        if isinstance(seg, tuple):
            out.append(f"[id={seg[1]}]")
        elif isinstance(seg, int):
            item = node[seg] if isinstance(node, list) and 0 <= seg < len(node) else None
            ident = next((item[f] for f in ("id", "key", "slug") if isinstance(item, dict) and f in item), None)
            out.append(f"[id={ident}]" if ident is not None else f"[{seg}]")
        else:
            out.append(seg)
        try:
            node = _step(node, seg, "") if node is not None else None
        except HookError:
            node = None
    return ".".join(out)


@dataclass(frozen=True)
class DeclarativeHook:
    """A mod's op list bound to its manifest. Implements ``ContentHook``."""

    manifest: ModManifest
    ops: tuple[Mapping[str, Any], ...]
    _sealed_ops: tuple[str, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.ops, tuple) or len(self.ops) > MAX_OPS:
            raise HookError("ops must be a tuple within limit")
        perms = set(self.manifest.permissions)
        sealed: list[str] = []
        for original in self.ops:
            if not isinstance(original, Mapping):
                raise HookError(f"unknown hook op {original!r}"[:200])
            # Validate a detached JSON snapshot, not caller-owned mutable data.
            # Once accepted, subsequent edits cannot change permissions or paths.
            op = _json_value(dict(original))
            if op.get("op") not in OVERRIDE_OPS | EXTEND_OPS:
                raise HookError(f"unknown hook op {op!r}"[:200])
            need = "override_content" if op["op"] in OVERRIDE_OPS else "add_content"
            if need not in perms:
                raise HookError(f"{self.manifest.mod_id}: op {op['op']} needs permission {need}")
            parse_path(op.get("path", ""))
            if self.manifest.targets and not any(
                    op["path"] == t or op["path"].startswith((t + ".", t + "[")) for t in self.manifest.targets):
                raise HookError(f"{self.manifest.mod_id}: path {op['path']} outside declared targets")
            if op["op"] in ("set", "merge", "append"):
                _json_value(op.get("value"))
            if op["op"] == "merge" and not isinstance(op.get("value"), dict):
                raise HookError("merge value must be an object")
            if op["op"] == "append" and not isinstance(op.get("value"), list):
                raise HookError("append value must be a list")
            if op["op"] == "scale":
                for k in ("factor", "min", "max"):
                    v = op.get(k, 1 if k == "factor" else None)
                    if v is not None and (isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v)):
                        raise HookError(f"scale {k} must be a finite number")
            sealed.append(json.dumps(op, sort_keys=True, separators=(",", ":"), allow_nan=False))
        object.__setattr__(self, "_sealed_ops", tuple(sealed))

    @classmethod
    def from_list(cls, manifest: ModManifest, ops: Any) -> DeclarativeHook:
        if not isinstance(ops, list):
            raise HookError("hooks must be a list of ops")
        return cls(manifest, tuple(_json_value(o) for o in ops))

    def override_keys(self, plan: Any) -> set[str]:
        return {_canonical(plan, parse_path(o["path"])) for o in (json.loads(raw) for raw in self._sealed_ops)
                if o["op"] in OVERRIDE_OPS}

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = copy.deepcopy(payload["plan"])
        for raw in self._sealed_ops:
            op = json.loads(raw)
            segs, path = parse_path(op["path"]), op["path"]
            parent = plan
            for seg in segs[:-1]:
                parent = _step(parent, seg, path)
            last, kind = segs[-1], op["op"]
            if kind in ("merge", "append", "scale"):
                target = _step(parent, last, path)
                if kind == "merge":
                    if not isinstance(target, dict):
                        raise HookError(f"{path}: merge target is not an object")
                    clash = sorted(set(op["value"]) & set(target))
                    if clash:
                        raise HookError(f"{path}: merge would overwrite {clash}; use set")
                    target.update(copy.deepcopy(op["value"]))
                elif kind == "append":
                    if not isinstance(target, list):
                        raise HookError(f"{path}: append target is not a list")
                    target.extend(copy.deepcopy(op["value"]))
                else:
                    if isinstance(target, bool) or not isinstance(target, int | float):
                        raise HookError(f"{path}: scale target is not a number")
                    try:
                        if not math.isfinite(target):
                            raise HookError(f"{path}: scale target is not finite")
                        v = target * op.get("factor", 1)
                        # Reject overflow before any clamping; an infinity must
                        # never become an apparently valid bounded result.
                        if not math.isfinite(v):
                            raise HookError(f"{path}: scale result is not finite")
                        v = max(v, op["min"]) if op.get("min") is not None else v
                        v = min(v, op["max"]) if op.get("max") is not None else v
                        if not math.isfinite(v):
                            raise HookError(f"{path}: scale result is not finite")
                        value = type(target)(v) if isinstance(target, int) else v
                    except (OverflowError, ValueError) as exc:
                        raise HookError(f"{path}: scale numeric overflow") from exc
                    self._assign(parent, last, value, path)
            elif kind == "set":
                if isinstance(parent, dict) and isinstance(last, str):
                    parent[last] = copy.deepcopy(op["value"])
                else:
                    self._assign(parent, last, copy.deepcopy(op["value"]), path)
            else:  # remove
                if isinstance(last, str):
                    _step(parent, last, path)
                    del parent[last]
                else:
                    del parent[last if isinstance(last, int) else _find(parent, last[1], path)]
        return plan

    @staticmethod
    def _assign(parent: Any, last: Any, value: Any, path: str) -> None:
        if isinstance(last, str):
            _step(parent, last, path)
            parent[last] = value
        else:
            idx = last if isinstance(last, int) else _find(parent, last[1], path)
            _step(parent, idx, path)
            parent[idx] = value


def apply_mods(plan: Mapping[str, Any], load_plan: LoadPlan,
               hooks: Mapping[str, DeclarativeHook]) -> dict[str, Any]:
    """Apply hooks in load order through a B095 ``Host`` (scopes = mod permissions).

    Two mods overriding the same key is a conflict unless the later mod explicitly
    orders itself after the earlier one (``depends``/``optional``/``load_after``).
    The input plan is never mutated; any failure leaves no partial result.
    """
    current: dict[str, Any] = _json_value(dict(plan))
    owners: dict[str, str] = {}
    for m in load_plan.order:
        hook = hooks.get(m.mod_id)
        if hook is None:
            continue
        if hook.manifest != m:
            raise HookError(f"hook for {m.mod_id} was built for a different manifest")
        for key in sorted(hook.override_keys(current)):
            prev = owners.get(key)
            if prev and not ordered_before(load_plan, prev, m.mod_id):
                raise HookError(f"override conflict on {key}: {prev} and {m.mod_id}")
            owners[key] = m.mod_id
        host = Host(frozenset(m.permissions))
        try:
            host.register(Manifest(m.mod_id, "content_hook", SDK_API, tuple(m.permissions)), hook)
            current = host.call(m.mod_id, "apply", {"plan": current})
        except HookError:
            raise
        except ContractError as exc:
            raise HookError(f"{m.mod_id}: {exc}") from exc
    return current
