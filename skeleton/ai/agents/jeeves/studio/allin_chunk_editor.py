"""All-in chunk editor with optical learning."""
from __future__ import annotations
from typing import Dict, Any

def edit_allin(chunk: str, optical: float) -> Dict[str, Any]:
    if not chunk or optical < 0.8:
        return {"ok": False, "reason": "floors", "learned": 0}
    learned = int(optical * 10)
    return {"ok": True, "chunk": chunk, "optical": optical, "learned": learned, "reason": "ok"}
