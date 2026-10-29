"""Learn patterns from optical-tagged chunks."""
from __future__ import annotations
from typing import Dict, Any

def learn_patterns(chunks: int, optical: float) -> Dict[str, Any]:
    if chunks < 1 or optical < 0.75:
        return {"ok": False, "reason": "floors", "patterns": 0}
    patterns = int(chunks * optical * 0.6)
    return {"ok": True, "chunks": chunks, "patterns": patterns, "optical": optical, "reason": "ok"}
