"""
Hive merkle gossip. Root history, tournament on roots, local helix jsonl consensus. No chain and no coin.
"""
from __future__ import annotations

import re

from .seam_runtime import admit, stamp

ROOTS: list[str] = []
_CAP = 64
_ROOT = re.compile(r"^[0-9a-f]{64}$")
_NODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def gossip(root: str) -> None:
    if not isinstance(root, str) or not (_ROOT.fullmatch(root) or _NODE.fullmatch(root)):
        raise ValueError("root is invalid")
    if root in ROOTS:
        return
    if len(ROOTS) >= _CAP:
        raise ValueError("root history is full")
    ROOTS.append(root)


def process(data: dict) -> dict:
    refused = admit("hive_chronicle", data)
    if refused:
        return refused
    root = data.get("root")
    if root is None:
        return stamp("hive_chronicle", data, {"roots": len(ROOTS)})
    try:
        gossip(root)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "card": "hive_chronicle"}
    return stamp("hive_chronicle", data, {"roots": len(ROOTS), "root": root})
