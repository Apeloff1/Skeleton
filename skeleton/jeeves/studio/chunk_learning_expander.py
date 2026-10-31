"""Expand chunk learning with optical patterns."""
from __future__ import annotations
from typing import Dict, Any

def expand_learning(chunks: int, optical: float) -> Dict[str, Any]:
    if chunks < 1 or optical < 0.75:
        return {"ok": False, "reason": "floors", "learned": 0}
    learned = int(chunks * optical)
    return {"ok": True, "chunks": chunks, "learned": learned, "optical": optical, "reason": "ok"}
