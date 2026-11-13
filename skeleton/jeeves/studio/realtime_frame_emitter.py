"""Emit realtime frame with optical blend."""
from __future__ import annotations
from typing import Dict, Any

def emit_frame(chunk: str, optical: float) -> Dict[str, Any]:
    if not chunk or optical < 0.8:
        return {"ok": False, "reason": "floors", "emitted": False}
    return {"ok": True, "chunk": chunk, "optical": optical, "emitted": True, "reason": "ok"}
