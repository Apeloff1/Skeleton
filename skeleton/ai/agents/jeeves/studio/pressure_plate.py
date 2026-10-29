"""Pressure plate. Triggers on weight."""
from typing import Any, Dict
class PressurePlate:
    def __init__(self):
        self.active = False
    def step(self, weight: float) -> bool:
        self.active = weight > 0.5
        return self.active
