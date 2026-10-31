"""Extract decomp weights with optical."""
from __future__ import annotations
from typing import Dict, Any

def extract_weights(source: str, optical: float) -> Dict[str, Any]:
    if not source or optical < 0.85:
        return {"ok": False, "reason": "floors", "weights": 0}
    weights = int(optical * 100)
    return {"ok": True, "source": source, "weights": weights, "optical": optical, "reason": "ok"}
