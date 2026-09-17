"""Content-addressed release graph for the build lane. No coin. No uuid."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


MAX_NODES = 32


class ReleaseGraphError(ValueError):
    """Release graph contract violation."""


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def node(*, name: str, body: Mapping[str, Any]) -> dict[str, Any]:
    label = str(name or "").strip()
    if not label or len(label) > 64:
        raise ReleaseGraphError("node name invalid")
    if not isinstance(body, Mapping):
        raise ReleaseGraphError("node body must be an object")
    payload = {"name": label, "body": dict(body), "stored_prose": 0}
    return {"kind": "release_node", "name": label, "digest": _digest(payload), "stored_prose": 0}


def graph(nodes: list[Mapping[str, Any]] | None) -> dict[str, Any]:
    rows = [node(name=str(item["name"]), body=dict(item.get("body") or {})) for item in (nodes or [])]
    if len(rows) > MAX_NODES:
        raise ReleaseGraphError("too many nodes")
    names = [row["name"] for row in rows]
    if len(names) != len(set(names)):
        raise ReleaseGraphError("node names must be unique")
    root = _digest({"nodes": [row["digest"] for row in rows], "stored_prose": 0})
    return {
        "kind": "release_graph",
        "n": len(rows),
        "nodes": rows,
        "root": root,
        "reproducible": True,
        "stored_prose": 0,
    }
