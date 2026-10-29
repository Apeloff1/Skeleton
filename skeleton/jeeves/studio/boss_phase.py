"""Boss phase.
Multi-phase boss with weak points and optical scaling.
"""
from typing import Any, Dict

class BossPhase:
    def sequence(self, phases: int, optical: float) -> Dict[str, Any]:
        if not isinstance(phases, int) or phases < 1:
            return {"ok": False, "reason": "bad_phases", "schema": "skeleton.boss.phase.v1"}
        seq = [{"phase": i+1, "weak": "core" if i == phases-1 else "armor", "hp": 100 - i*10, "optical": optical} for i in range(phases)]
        return {"ok": True, "phases": seq, "count": phases, "optical": optical, "reason": "ok", "schema": "skeleton.boss.phase.v1"}
