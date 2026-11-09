"""GB-43 mesh scan. Counts sentence hits. Does not keep them."""

from __future__ import annotations


def scan(card: object) -> dict:
    hits = 0

    def walk(node: object, depth: int) -> None:
        nonlocal hits
        if depth > 6 or hits >= 32:
            return
        if isinstance(node, str):
            if " " in node.strip():
                hits += 1
            return
        if isinstance(node, dict):
            for value in node.values():
                walk(value, depth + 1)
            return
        if isinstance(node, (list, tuple)):
            for value in node:
                walk(value, depth + 1)

    walk(card, 0)
    return {
        "kind": "mesh",
        "hits": hits,
        "doctor": 1 if hits else 0,
        "stored_prose": 0,
    }
