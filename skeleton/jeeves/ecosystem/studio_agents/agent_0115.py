"""Studio agent 0115.
"""
from __future__ import annotations

AGENT = "studio_agent_0115"

def run(brief: str, era: str = "ash") -> dict:
    if not brief:
        return {"ok": False, "reason": "empty_brief"}
    return {"ok": True, "agent": AGENT, "brief": brief[:200], "era": era, "output": "emitted"}
