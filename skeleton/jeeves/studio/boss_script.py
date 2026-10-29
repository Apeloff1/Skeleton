"""Boss script.
Phase and optical for boss.gd.
"""
from typing import Any, Dict

class BossScript:
    def emit(self, phase: str, optical: float) -> Dict[str, Any]:
        if not isinstance(phase, str) or not phase.strip():
            return {"ok": False, "reason": "empty_phase", "schema": "skeleton.boss.script.v1"}
        text = f"var phase = \\\"{phase}\\\"\\nvar optical = {optical}"
        return {"ok": True, "phase": phase, "optical": optical, "text": text, "reason": "ok", "schema": "skeleton.boss.script.v1"}
