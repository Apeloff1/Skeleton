"""Install guard.
Fail-closed check for first install: local AI, peak, Godot, and optical.
"""
from typing import Any, Dict

class InstallGuard:
    def check(self, ai_ok: bool, peak: bool, godot_ok: bool, optical: float, fidelity: float) -> Dict[str, Any]:
        if not isinstance(optical, (int, float)) or not isinstance(fidelity, (int, float)):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.install.guard.v1"}
        ok = bool(ai_ok) and bool(peak) and bool(godot_ok) and optical >= 0.9 and fidelity >= 0.92
        return {
            "ok": ok,
            "ai_ok": bool(ai_ok),
            "peak": bool(peak),
            "godot_ok": bool(godot_ok),
            "optical": optical,
            "fidelity": fidelity,
            "reason": "ok" if ok else "gates_failed",
            "schema": "skeleton.install.guard.v1",
        }
