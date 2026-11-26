"""Refined systems at highest level.
Detailed interlocking with how/why/when.
"""
from typing import Dict, Any

class RefinedSystems:
    def design(self) -> Dict[str, Any]:
        return {
            "inventory": {"how": "slots + weight + rarity", "why": "constrains and rewards choices", "when": "always available"},
            "combat": {"how": "consumes inventory, produces progression currency", "why": "creates risk-reward", "when": "encounter"},
            "progression": {"how": "gates narrative beats and new verbs", "why": "mastery and purpose", "when": "after meaningful success"},
            "narrative": {"how": "reframes earlier systems", "why": "emotional payoff", "when": "mid and end"},
            "interlocked": True,
            "highest": True
        }
