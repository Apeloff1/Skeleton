"""Peak seal.
Final fail-closed seal for install and use. Requires all gates.
"""
from typing import Any, Dict

class PeakSeal:
    def seal(self, fidelity: float, optical: float, ai_ok: bool, peak: bool, godot_ok: bool, export_ok: bool) -> Dict[str, Any]:
        if not all(isinstance(x, (int, float)) for x in (fidelity, optical)):
            return {"sealed": False, "reason": "bad_types", "schema": "skeleton.peak.seal.v1"}
        sealed = (
            fidelity >= 0.94
            and optical >= 0.9
            and bool(ai_ok)
            and bool(peak)
            and bool(godot_ok)
            and bool(export_ok)
        )
        return {
            "sealed": sealed,
            "fidelity": fidelity,
            "optical": optical,
            "ai_ok": bool(ai_ok),
            "peak": bool(peak),
            "godot_ok": bool(godot_ok),
            "export_ok": bool(export_ok),
            "reason": "ok" if sealed else "gates_failed",
            "schema": "skeleton.peak.seal.v1",
        }
