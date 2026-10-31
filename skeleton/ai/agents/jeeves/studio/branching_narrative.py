"""Branching narrative (10x).
Acts driven by optical diversity and economy state, choice points, ending variants.
"""
from __future__ import annotations
from typing import Any, Dict, List

class BranchingNarrative:
    def __init__(self):
        self.act = 0
        self.choices = []
        self.ending = None

    def advance(self, optical: float, salvage: int) -> Dict[str, Any]:
        self.act += 1
        branch = "high_optical" if optical > 0.9 else "standard"
        if salvage > 40:
            branch = "wealthy"
        prompt = f"Act {self.act}: tunnels respond to {branch}"
        choice = {"act": self.act, "branch": branch, "prompt": prompt}
        self.choices.append(choice)
        if self.act >= 5:
            self.ending = "extract" if salvage > 30 else "remain"
        return {"act": self.act, "branch": branch, "prompt": prompt, "ending": self.ending}

    def sequence(self) -> List[Dict[str, Any]]:
        return self.choices
