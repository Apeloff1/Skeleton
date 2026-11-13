"""Difficulty preset. Named difficulty curves."""
from typing import Any, Dict
PRESETS = {"easy": 0.7, "normal": 1.0, "hard": 1.4, "ash": 1.8}
class DifficultyPreset:
    def apply(self, name: str) -> float:
        return PRESETS.get(name, 1.0)
