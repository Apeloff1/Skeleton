"""First install readiness.
Checks local AI, peak gates, and end-user surface for clean first run.
"""
from typing import Any, Dict

class FirstInstall:
    def check(self, ai_ok: bool, peak: bool, fidelity: float, optical: float) -> Dict[str, Any]:
        ready = ai_ok and peak and fidelity >= 0.92 and optical >= 0.9
        return {
            "ready": ready,
            "ai_ok": ai_ok,
            "peak": peak,
            "fidelity": fidelity,
            "optical": optical,
            "first_run": True,
            "schema": "skeleton.first_install.v1",
        }
