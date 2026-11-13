"""Skill tree 008.
"""
from __future__ import annotations

TREE = "tree_008"

def nodes() -> list[str]:
    return ["root", "branch_a", "branch_b", "capstone"]

def can_unlock(node: str, owned: list[str]) -> bool:
    if node == "root":
        return True
    return "root" in owned
