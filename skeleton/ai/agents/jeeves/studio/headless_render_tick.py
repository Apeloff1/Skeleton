"""Headless render tick with optical and chunk."""
from __future__ import annotations
from typing import Dict, Any

def render_tick(tick: int, chunk: str, optical: float) -> Dict[str, Any]:
    if tick < 0 or optical < 0.8:
        return {"ok": False, "reason": "floors", "rendered": False}
    return {"ok": True, "tick": tick, "chunk": chunk, "optical": optical, "rendered": True, "reason": "ok"}
