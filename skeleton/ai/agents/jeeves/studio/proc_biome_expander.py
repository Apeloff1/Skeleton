"""Expand procedural biomes from era and optical."""
from __future__ import annotations
from typing import Dict, Any, List

def expand_biomes(era: str, optical: float, count: int) -> Dict[str, Any]:
    if count < 1 or optical < 0.8 or not era:
        return {"ok": False, "reason": "floors", "biomes": []}
    biomes = [f"{era}_tunnel", f"{era}_vault", f"{era}_ridge"]
    if optical > 0.9:
        biomes.append(f"{era}_core")
    return {"ok": True, "era": era, "biomes": biomes[:count], "optical": optical, "reason": "ok"}
