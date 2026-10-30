"""Content scale 0064.
"""
from __future__ import annotations

CONTENT = "content_0064"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][64 % 4], "rarity": ["common", "rare", "epic"][64 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
