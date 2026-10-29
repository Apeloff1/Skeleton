"""Deep persist realtime chunks."""
from __future__ import annotations
from typing import Dict, Any

def persist_deep(chunks: int, optical: float) -> Dict[str, Any]:
    if chunks < 1 or optical < 0.8:
        return {"ok": False, "reason": "floors", "persisted": 0}
    return {"ok": True, "chunks": chunks, "optical": optical, "persisted": chunks, "reason": "ok"}
