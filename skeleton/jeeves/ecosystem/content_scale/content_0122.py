"""Content scale 0122.
"""
from __future__ import annotations

CONTENT = "content_0122"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][122 % 4], "rarity": ["common", "rare", "epic"][122 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
