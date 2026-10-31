"""Advanced decomp weight extractor.
Multi-era modulation, optical bias, and phase-projection fusion.
"""
from typing import Any, Dict

class DecompWeightExtractor:
    ERAS = ["nes", "snes", "gb", "gbc", "gba", "n64", "ps1", "ps2", "dreamcast", "arcade", "ash", "crystal", "void", "rift", "core", "ember", "ice", "prism"]

    def extract(self, patterns: Dict[str, Any], optical: float = 0.93, era: str = "ash") -> Dict[str, float]:
        phases = patterns.get("inferred_phases", 5)
        projections = len(patterns.get("verified_projections", []))
        base = min(1.0, (phases / 6) * 0.5 + (projections / 5) * 0.5)
        era_bias = 1.05 if era in ["ps2", "dreamcast", "n64"] else 1.0 if era in self.ERAS else 0.95
        return {
            "decomp": round(base * era_bias, 3),
            "distill": round(min(0.99, 0.88 + optical * 0.06), 3),
            "weight": round(base * optical * era_bias, 3),
            "forge": round(0.7 + base * 0.2 * era_bias, 3),
            "optical": optical,
            "boss": round(0.6 + phases * 0.05 * era_bias, 3),
            "loot": round(0.5 + projections * 0.04 * era_bias, 3),
            "narrative": round(0.55 + optical * 0.2, 3),
            "economy": round(0.6 + base * 0.15 * era_bias, 3),
            "ai": round(0.65 + optical * 0.2 * era_bias, 3),
            "era_bias": era_bias,
        }
