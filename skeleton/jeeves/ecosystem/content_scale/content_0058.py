"""Content scale 0058.
"""
from __future__ import annotations

CONTENT = "content_0058"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][58 % 4], "rarity": ["common", "rare", "epic"][58 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
