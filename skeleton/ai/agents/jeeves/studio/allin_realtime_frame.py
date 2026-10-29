"""All-in realtime frame emitter."""
from __future__ import annotations
from typing import Dict, Any

def frame_allin(chunk: str, optical: float) -> Dict[str, Any]:
    if not chunk or optical < 0.8:
        return {"ok": False, "reason": "floors", "emitted": False}
    return {"ok": True, "chunk": chunk, "optical": optical, "emitted": True, "reason": "ok"}
