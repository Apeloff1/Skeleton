"""systems_lead agent — loops and economy.
Part of the full-scale ecosystem multi-agent toolkit.
"""
from __future__ import annotations
from typing import Any

class SystemsLeadAgent:
    role = "loops and economy"

    def __init__(self, era: str = "ash", optical: float = 0.95) -> None:
        self.era = era
        self.optical = max(0.0, min(1.0, optical))


    def loop(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "systems_lead",
            "method": "loop",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

    def economy(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "systems_lead",
            "method": "economy",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

    def progression(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "systems_lead",
            "method": "progression",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

def run(brief: str, era: str = "ash") -> dict[str, Any]:
    agent = SystemsLeadAgent(era=era)
    return agent.loop(brief)
