"""Optical gate for economy pricing."""
from __future__ import annotations
from typing import Dict, Any

def gate_economy(price: float, optical: float) -> Dict[str, Any]:
    if price < 0 or optical < 0.8:
        return {"ok": False, "reason": "floors", "adjusted": price}
    adjusted = price * (1.0 + optical * 0.2)
    return {"ok": True, "price": price, "adjusted": adjusted, "optical": optical, "reason": "ok"}
