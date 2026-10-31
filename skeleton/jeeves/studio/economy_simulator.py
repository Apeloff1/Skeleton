"""Economy simulator.
Dynamic pricing, salvage flow, and optical-driven value modifiers.
"""
from typing import Any, Dict

class EconomySimulator:
    def __init__(self):
        self.salvage = 0
        self.prices = {"speed": 20, "armor": 25, "range": 18}

    def earn(self, amount: int, optical: float) -> int:
        gained = int(amount * (1.0 + optical * 0.3))
        self.salvage += gained
        return gained

    def spend(self, item: str) -> bool:
        cost = self.prices.get(item, 999)
        if self.salvage < cost:
            return False
        self.salvage -= cost
        return True

    def status(self) -> Dict[str, Any]:
        return {"salvage": self.salvage, "prices": self.prices, "schema": "skeleton.economy.sim.v1"}
