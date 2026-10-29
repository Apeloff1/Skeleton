"""First install readiness.
Fail-closed: refuses ready unless AI, peak, fidelity, and optical all pass.
"""
from typing import Any, Dict

class FirstInstall:
    def check(self, ai_ok: bool, peak: bool, fidelity: float, optical: float) -> Dict[str, Any]:
        if not isinstance(fidelity, (int, float)) or not isinstance(optical, (int, float)):
            return {"ready": False, "reason": "bad_types", "schema": "skeleton.first_install.v2"}
        ready = bool(ai_ok) and bool(peak) and fidelity >= 0.92 and optical >= 0.9
        return {
            "ready": ready,
            "ai_ok": bool(ai_ok),
            "peak": bool(peak),
            "fidelity": fidelity,
            "optical": optical,
            "first_run": True,
            "reason": "ok" if ready else "gates_failed",
            "schema": "skeleton.first_install.v2",
        }
