"""Optical-weighted learning engine for chunked editor.
Fail-closed on low diversity."""
from __future__ import annotations
from typing import Dict, Any, List

def learn_from_chunks(chunks: List[Dict[str, Any]], optical: float) -> Dict[str, Any]:
    if not isinstance(chunks, list) or optical < 0.5:
        return {"ok": False, "reason": "low_optical_or_bad_input", "learned": 0}
    learned = sum(1 for c in chunks if c.get("optical", 0) > 0.6)
    return {"ok": True, "learned": learned, "optical": optical, "reason": "ok"}
