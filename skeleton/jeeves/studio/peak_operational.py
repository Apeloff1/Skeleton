"""Peak operational.
Aggregates fidelity, optical, export, and local AI readiness.
"""
from typing import Any, Dict

class PeakOperational:
    def check(self, fidelity: float, optical: float, export_ok: bool, ai_ok: bool) -> Dict[str, Any]:
        peak = fidelity >= 0.94 and optical >= 0.9 and export_ok and ai_ok
        return {
            "peak": peak,
            "fidelity": fidelity,
            "optical": optical,
            "export_ok": export_ok,
            "ai_ok": ai_ok,
            "schema": "skeleton.peak.v1",
        }
