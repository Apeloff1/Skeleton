"""Frontend bridge. Complete contracts for Jeeves, Forge, Cockpit.
Beta tester ready. No stubs.
"""
from typing import Dict, Any

class FrontendBridge:
    def jeeves_contract(self) -> Dict:
        return {
            "endpoints": ["/jeeves/start", "/jeeves/respond"],
            "response_shape": {"response": str, "quality": float, "beta_ready": bool},
            "ui": "chat panel with history, citations, steer indicator"
        }

    def forge_contract(self) -> Dict:
        return {
            "endpoints": ["/forge/execute", "/forge/emit"],
            "response_shape": {"run_id": str, "status": str, "godot_ready": bool},
            "ui": "brief input, progress steps, download pack button"
        }

    def cockpit_contract(self) -> Dict:
        return {
            "endpoints": ["/cockpit/critique/{run_id}"],
            "response_shape": {"weakest": str, "scores": dict},
            "ui": "4-axis radar + balance card"
        }
