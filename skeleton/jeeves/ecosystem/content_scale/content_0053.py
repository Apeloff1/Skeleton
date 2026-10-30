"""Content scale 0053.
"""
from __future__ import annotations

CONTENT = "content_0053"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][53 % 4], "rarity": ["common", "rare", "epic"][53 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
