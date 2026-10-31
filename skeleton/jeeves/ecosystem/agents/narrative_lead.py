"""narrative_lead agent — branching dialogue.
Part of the full-scale ecosystem multi-agent toolkit.
"""
from __future__ import annotations
from typing import Any

class NarrativeLeadAgent:
    role = "branching dialogue"

    def __init__(self, era: str = "ash", optical: float = 0.95) -> None:
        self.era = era
        self.optical = max(0.0, min(1.0, optical))


    def opening(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "narrative_lead",
            "method": "opening",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

    def mid_branch(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "narrative_lead",
            "method": "mid_branch",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

    def ending(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "narrative_lead",
            "method": "ending",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

def run(brief: str, era: str = "ash") -> dict[str, Any]:
    agent = NarrativeLeadAgent(era=era)
    return agent.opening(brief)
