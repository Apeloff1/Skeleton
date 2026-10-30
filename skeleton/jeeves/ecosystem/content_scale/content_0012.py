"""Content scale 0012.
"""
from __future__ import annotations

CONTENT = "content_0012"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][12 % 4], "rarity": ["common", "rare", "epic"][12 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
