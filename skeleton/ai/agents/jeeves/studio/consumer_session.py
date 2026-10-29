"""Consumer session.
Tracks build progress, optical, and seal for end-user runs.
"""
from typing import Any, Dict

class ConsumerSession:
    def __init__(self):
        self.progress = 0.0
        self.sealed = False

    def step(self, brief: str, optical: float) -> Dict[str, Any]:
        if not isinstance(brief, str) or not brief.strip():
            return {"ok": False, "reason": "empty_brief", "schema": "skeleton.consumer.session.v1"}
        self.progress = min(1.0, self.progress + 0.25)
        self.sealed = self.progress >= 1.0 and optical >= 0.9
        return {
            "ok": True,
            "progress": round(self.progress, 2),
            "sealed": self.sealed,
            "optical": optical,
            "reason": "ok" if self.sealed else "in_progress",
            "schema": "skeleton.consumer.session.v1",
        }
