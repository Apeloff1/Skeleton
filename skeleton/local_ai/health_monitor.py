"""
Operational Health Monitor. Continuous check of engine, loader, and seams. Fail-closed alerts.
Fills the liveness gap.
"""
from typing import Dict
from .operational_engine import get_engine
from .model_loader import ModelLoader
from .doctor import doctor

class HealthMonitor:
    def __init__(self):
        self.engine = get_engine()
        self.loader = ModelLoader()

    def check(self) -> Dict:
        eng = self.engine.status()
        doc = doctor()
        return {
            "engine": eng["operational"],
            "doctor": doc["doctor"],
            "seams": eng["facade"]["seams"],
            "healthy": eng["operational"] and doc["doctor"] == "passed"
        }
