"""procgen_lead agent — noise and graphs.
Part of the full-scale ecosystem multi-agent toolkit.
"""
from __future__ import annotations
from typing import Any

class ProcgenLeadAgent:
    role = "noise and graphs"

    def __init__(self, era: str = "ash", optical: float = 0.95) -> None:
        self.era = era
        self.optical = max(0.0, min(1.0, optical))


    def noise(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "procgen_lead",
            "method": "noise",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

    def rooms(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "procgen_lead",
            "method": "rooms",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

    def loot(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "procgen_lead",
            "method": "loot",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

def run(brief: str, era: str = "ash") -> dict[str, Any]:
    agent = ProcgenLeadAgent(era=era)
    return agent.noise(brief)
