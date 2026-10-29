"""Studio agent 0038.
"""
from __future__ import annotations

AGENT = "studio_agent_0038"

def run(brief: str, era: str = "ash") -> dict:
    if not brief:
        return {"ok": False, "reason": "empty_brief"}
    return {"ok": True, "agent": AGENT, "brief": brief[:200], "era": era, "output": "emitted"}
