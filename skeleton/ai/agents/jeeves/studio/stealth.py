"""Stealth. Detection radius based on optical and movement."""
from typing import Any, Dict
class Stealth:
    def detection_radius(self, optical: float, moving: bool) -> float:
        base = 8.0 if moving else 4.0
        return base * (1.2 - optical * 0.3)
