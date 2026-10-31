"""Accessibility options.
Adjusts optical thresholds, hazard intensity, and tutorial pacing.
"""
from __future__ import annotations
from typing import Any, Dict

class AccessibilityOptions:
    def __init__(self):
        self.reduced_hazard = False
        self.slower_tutorial = False
        self.higher_optical_ease = False
    def set(self, key: str, value: bool) -> None:
        if hasattr(self, key):
            setattr(self, key, value)
    def adjust_hazard(self, damage: int) -> int:
        return max(0, damage // 2) if self.reduced_hazard else damage
    def adjust_optical_target(self, target: float) -> float:
        return max(0.7, target - 0.05) if self.higher_optical_ease else target
    def status(self) -> Dict[str, Any]:
        return {
            "reduced_hazard": self.reduced_hazard,
            "slower_tutorial": self.slower_tutorial,
            "higher_optical_ease": self.higher_optical_ease,
        }
