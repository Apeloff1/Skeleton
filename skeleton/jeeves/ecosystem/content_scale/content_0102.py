"""Content scale 0102.
"""
from __future__ import annotations

CONTENT = "content_0102"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][102 % 4], "rarity": ["common", "rare", "epic"][102 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
