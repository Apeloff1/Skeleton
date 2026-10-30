"""Content scale 0038.
"""
from __future__ import annotations

CONTENT = "content_0038"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][38 % 4], "rarity": ["common", "rare", "epic"][38 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
