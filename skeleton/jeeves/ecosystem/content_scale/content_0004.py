"""Content scale 0004.
"""
from __future__ import annotations

CONTENT = "content_0004"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][4 % 4], "rarity": ["common", "rare", "epic"][4 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
