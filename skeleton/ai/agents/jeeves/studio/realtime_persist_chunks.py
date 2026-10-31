"""Persist realtime chunks with optical tags."""
from __future__ import annotations
from typing import Dict, Any

def persist_chunks(chunk_count: int, optical: float) -> Dict[str, Any]:
    if optical < 0.8:
        return {"ok": False, "reason": "optical_floor", "persisted": 0}
    return {"ok": True, "chunks": chunk_count, "optical_tagged": True, "learned": int(optical * chunk_count), "reason": "ok"}
