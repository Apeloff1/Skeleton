"""B097: three-way semantic merge of IR scene graphs with explicit irreducible conflicts."""

from __future__ import annotations

from typing import Any

from ._helpers import digest

_MISSING = object()


def _get(d: dict, k: str) -> Any:
    return d.get(k, _MISSING)


def merge_nodes(base: dict[str, dict], ours: dict[str, dict], theirs: dict[str, dict]):
    """Per-node, per-field merge. Returns (merged, conflicts)."""
    merged: dict[str, dict] = {}
    conflicts: list[dict[str, Any]] = []
    for nid in sorted(set(base) | set(ours) | set(theirs)):
        b, o, t = _get(base, nid), _get(ours, nid), _get(theirs, nid)
        if o is _MISSING and t is _MISSING:
            continue
        if b is _MISSING:
            if o is not _MISSING and t is not _MISSING and digest(o) != digest(t):
                conflicts.append({"node": nid, "kind": "add_add"})
                continue
            merged[nid] = o if o is not _MISSING else t
            continue
        if o is _MISSING or t is _MISSING:
            survivor = t if o is _MISSING else o
            if digest(survivor) != digest(b):
                conflicts.append({"node": nid, "kind": "delete_modify"})
            continue
        node: dict[str, Any] = {}
        for f in sorted(set(b) | set(o) | set(t)):
            bf, of, tf = _get(b, f), _get(o, f), _get(t, f)
            if isinstance(bf, dict) and isinstance(of, dict) and isinstance(tf, dict):
                sub, sc = merge_nodes({"_": bf}, {"_": of}, {"_": tf})
                conflicts += [{"node": nid, "field": f, **c} for c in sc]
                if "_" in sub:
                    node[f] = sub["_"]
                continue
            if digest_safe(of) == digest_safe(tf):
                pick = of
            elif digest_safe(of) == digest_safe(bf):
                pick = tf
            elif digest_safe(tf) == digest_safe(bf):
                pick = of
            else:
                conflicts.append({"node": nid, "field": f, "kind": "field"})
                pick = bf
            if pick is not _MISSING:
                node[f] = pick
        merged[nid] = node
    _check_parents(merged, conflicts)
    return merged, conflicts


def digest_safe(v: Any) -> str:
    return "<missing>" if v is _MISSING else digest(v)


def _check_parents(merged: dict[str, dict], conflicts: list) -> None:
    for nid, n in sorted(merged.items()):
        p = n.get("parent") if isinstance(n, dict) else None
        if p is not None and p not in merged:
            conflicts.append({"node": nid, "kind": "orphaned"})
