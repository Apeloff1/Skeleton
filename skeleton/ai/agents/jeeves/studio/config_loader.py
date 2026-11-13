"""Config loader.
Loads pipeline defaults and overrides from a dict or file-like source.
"""
from __future__ import annotations
from typing import Any, Dict

DEFAULTS = {
    "optical_threshold": 0.92,
    "fidelity_min": 0.92,
    "mass_clip": 1.1,
    "seed": 8847291,
    "lang": "en",
}

class ConfigLoader:
    def __init__(self, overrides: Dict[str, Any] = None):
        self.config = dict(DEFAULTS)
        if overrides:
            self.config.update(overrides)
    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)
    def all(self) -> Dict[str, Any]:
        return dict(self.config)
