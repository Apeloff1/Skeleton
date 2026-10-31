"""Consumer progress.
Tracks multi-step build progress for end users.
"""
from typing import Any, Dict

class ConsumerProgress:
    STEPS = ["brief", "generate", "validate", "seal"]

    def advance(self, step: str, optical: float) -> Dict[str, Any]:
        if step not in self.STEPS:
            return {"ok": False, "reason": "bad_step", "schema": "skeleton.progress.v1"}
        idx = self.STEPS.index(step)
        return {"ok": True, "step": step, "index": idx, "total": len(self.STEPS), "optical": optical, "reason": "ok", "schema": "skeleton.progress.v1"}
