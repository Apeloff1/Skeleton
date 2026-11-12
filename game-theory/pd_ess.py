"""Prisoner's Dilemma dynamics and evolutionary stable strategies.
"""
from typing import Dict, Any

class PrisonersDilemmaESS:
    def analyze(self) -> Dict[str, Any]:
        T, R, P, S = 5, 3, 1, 0
        payoffs = {
            "cooperate_cooperate": R,
            "cooperate_defect": S,
            "defect_cooperate": T,
            "defect_defect": P
        }
        return {
            "payoffs": payoffs,
            "one_shot_dominant": "defect",
            "evolutionary_note": "Tit-for-Tat or similar can be ESS in repeated interactions",
            "ess_candidates": ["always_defect", "tit_for_tat"],
            "dynamics": "replicator favors higher payoff; cooperation emerges with reciprocity",
            "analyzed": True
        }
