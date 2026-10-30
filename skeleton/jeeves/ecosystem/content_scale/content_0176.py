"""Content scale 0176.
"""
from __future__ import annotations

CONTENT = "content_0176"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][176 % 4], "rarity": ["common", "rare", "epic"][176 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
