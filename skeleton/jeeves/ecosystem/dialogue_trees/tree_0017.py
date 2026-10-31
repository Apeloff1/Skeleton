"""Dialogue tree 0017.
"""
from __future__ import annotations

TREE = "dtree_0017"

def nodes() -> list[str]:
    return ["root", "branch_a", "branch_b", "end"]

def choose(node: str, option: int) -> dict:
    if not node:
        return {"ok": False, "reason": "no_node"}
    return {"ok": True, "tree": TREE, "node": node, "option": option, "next": "end" if option else "branch_a"}
