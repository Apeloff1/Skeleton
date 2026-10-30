"""Content scale 0097.
"""
from __future__ import annotations

CONTENT = "content_0097"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][97 % 4], "rarity": ["common", "rare", "epic"][97 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
