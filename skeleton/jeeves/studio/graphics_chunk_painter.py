"""Paint chunks with era palette and optical."""
from __future__ import annotations
from typing import Dict, Any

def paint_chunk(chunk_id: str, era: str, optical: float) -> Dict[str, Any]:
    if not chunk_id or not era or optical < 0.75:
        return {"ok": False, "reason": "floors", "painted": False}
    return {"ok": True, "chunk": chunk_id, "era": era, "optical": optical, "painted": True, "reason": "ok"}
