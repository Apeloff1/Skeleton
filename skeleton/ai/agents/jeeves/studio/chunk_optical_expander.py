"""Expand chunks with optical learning consistency."""
from __future__ import annotations
from typing import Dict, Any, List

def expand_chunks(existing: List[str], optical: float) -> Dict[str, Any]:
    if optical < 0.85:
        return {"ok": False, "reason": "optical_floor", "chunks": existing}
    new = [f"chunk_{i}" for i in range(len(existing), len(existing)+4)]
    return {"ok": True, "chunks": existing + new, "learned": len(existing)+4, "reason": "ok"}
