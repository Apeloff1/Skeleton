"""
Operational Config Loader. Loads and validates against schema. Fail-closed on invalid.
Fills the config gap.
"""
from typing import Dict
from .config_schema import SCHEMA
from .fail_closed import guard_schema

class ConfigLoader:
    def __init__(self):
        self.config: Dict = {"lora_rank": 8, "clip_factor": 1.1, "cas_min_length": 16}

    def load(self, overrides: Dict = None) -> Dict:
        if overrides:
            self.config.update(overrides)
        guard_schema(self.config)
        return self.config.copy()
