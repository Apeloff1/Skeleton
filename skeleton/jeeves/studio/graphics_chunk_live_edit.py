"""Live edit chunk with optical consistency."""
from __future__ import annotations
from typing import Dict, Any

def live_edit(chunk: str, optical: float) -> Dict[str, Any]:
    if not chunk or optical < 0.8:
        return {"ok": False, "reason": "floors", "edited": False}
    return {"ok": True, "chunk": chunk, "optical": optical, "edited": True, "reason": "ok"}
