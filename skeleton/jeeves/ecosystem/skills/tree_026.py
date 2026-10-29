"""Skill tree 026.
"""
from __future__ import annotations

TREE = "tree_026"

def nodes() -> list[str]:
    return ["root", "branch_a", "branch_b", "capstone"]

def can_unlock(node: str, owned: list[str]) -> bool:
    if node == "root":
        return True
    return "root" in owned
