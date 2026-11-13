"""
Enterprise Configuration. Schema-validated, fail-closed defaults for production workloads.
"""
from typing import Dict
from .config_loader import ConfigLoader
from .config_schema import SCHEMA

ENTERPRISE_DEFAULTS = {
    "lora_rank": 16,
    "clip_factor": 1.05,
    "cas_min_length": 32,
    "rate_capacity": 120,
    "max_context_turns": 32,
    "audit_enabled": True,
    "health_interval": 60,
    "batch_size": 8
}

class EnterpriseConfig:
    def __init__(self):
        self.loader = ConfigLoader()
        self.config = ENTERPRISE_DEFAULTS.copy()

    def load(self, overrides: Dict = None) -> Dict:
        base = self.loader.load(overrides or {})
        self.config.update(base)
        # Extra enterprise guards
        if self.config["cas_min_length"] < 16:
            raise ValueError("enterprise CAS min length too low")
        return self.config.copy()
