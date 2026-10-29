"""Reputation.
Score and tier with optical actions.
"""
from typing import Any, Dict

class Reputation:
    def update(self, score: int, actions: int, optical: float) -> Dict[str, Any]:
        if not isinstance(score, int) or not isinstance(actions, int):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.rep.v1"}
        tier = "known" if score > 10 else "unknown"
        return {"ok": True, "score": score, "tier": tier, "actions": actions, "optical": optical, "reason": "ok", "schema": "skeleton.rep.v1"}
