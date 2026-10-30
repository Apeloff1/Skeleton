"""Content scale 0158.
"""
from __future__ import annotations

CONTENT = "content_0158"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][158 % 4], "rarity": ["common", "rare", "epic"][158 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
