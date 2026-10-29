"""Procedural biome expander with era bias."""
from __future__ import annotations
from typing import Dict, Any, List

def expand_biomes(base: List[str], era: str, optical: float) -> Dict[str, Any]:
    if optical < 0.7:
        return {"ok": False, "reason": "optical_floor", "biomes": base}
    extras = [f"{era}_{b}" for b in ["rift", "vault", "spire"]]
    return {"ok": True, "biomes": base + extras, "count": len(base) + 3, "reason": "ok"}
