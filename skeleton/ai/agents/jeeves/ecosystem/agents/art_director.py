"""art_director agent — palette and style.
Part of the full-scale ecosystem multi-agent toolkit.
"""
from __future__ import annotations
from typing import Any

class ArtDirectorAgent:
    role = "palette and style"

    def __init__(self, era: str = "ash", optical: float = 0.95) -> None:
        self.era = era
        self.optical = max(0.0, min(1.0, optical))


    def palette(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "art_director",
            "method": "palette",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

    def style_tags(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "art_director",
            "method": "style_tags",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

    def respray(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "art_director",
            "method": "respray",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

def run(brief: str, era: str = "ash") -> dict[str, Any]:
    agent = ArtDirectorAgent(era=era)
    return agent.palette(brief)
