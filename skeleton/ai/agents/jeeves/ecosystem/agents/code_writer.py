"""code_writer agent — emits era-bound scripts.
Part of the full-scale ecosystem multi-agent toolkit.
"""
from __future__ import annotations
from typing import Any

class CodeWriterAgent:
    role = "emits era-bound scripts"

    def __init__(self, era: str = "ash", optical: float = 0.95) -> None:
        self.era = era
        self.optical = max(0.0, min(1.0, optical))


    def emit_player(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "code_writer",
            "method": "emit_player",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

    def emit_boss(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "code_writer",
            "method": "emit_boss",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

    def emit_cutscene(self, brief: str = "", **kwargs: Any) -> dict[str, Any]:
        if not brief and not kwargs:
            return {"ok": False, "reason": "empty_input"}
        return {
            "ok": True,
            "agent": "code_writer",
            "method": "emit_cutscene",
            "era": self.era,
            "optical": self.optical,
            "brief": (brief or "")[:240],
            "payload": dict(kwargs),
        }

def run(brief: str, era: str = "ash") -> dict[str, Any]:
    agent = CodeWriterAgent(era=era)
    return agent.emit_player(brief)
