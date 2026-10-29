"""Decomp weight extractor.
Turns decompilation outputs into the weight dict the pipeline expects.
"""
from typing import Any, Dict

class DecompWeightExtractor:
    def extract(self, patterns: Dict[str, Any], optical: float = 0.93) -> Dict[str, float]:
        phases = patterns.get("inferred_phases", 5)
        projections = len(patterns.get("verified_projections", []))
        base = min(1.0, (phases / 6) * 0.5 + (projections / 5) * 0.5)
        return {
            "decomp": round(base, 3),
            "distill": round(min(0.99, 0.88 + optical * 0.06), 3),
            "weight": round(base * optical, 3),
            "forge": round(0.7 + base * 0.2, 3),
            "optical": optical,
            "boss": round(0.6 + phases * 0.05, 3),
            "loot": round(0.5 + projections * 0.04, 3),
            "narrative": round(0.55 + optical * 0.2, 3),
            "economy": round(0.6 + base * 0.15, 3),
            "ai": round(0.65 + optical * 0.2, 3),
        }
