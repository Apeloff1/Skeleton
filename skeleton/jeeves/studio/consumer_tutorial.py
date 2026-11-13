"""Consumer tutorial.
First-run steps for end users.
"""
from typing import Any, Dict

class ConsumerTutorial:
    STEPS = ["brief", "generate", "seal", "export"]

    def step(self, index: int) -> Dict[str, Any]:
        if not isinstance(index, int) or index < 0 or index >= len(self.STEPS):
            return {"ok": False, "reason": "bad_index", "schema": "skeleton.tutorial.v1"}
        return {"ok": True, "index": index, "step": self.STEPS[index], "total": len(self.STEPS), "reason": "ok", "schema": "skeleton.tutorial.v1"}
