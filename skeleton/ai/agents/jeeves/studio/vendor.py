"""Vendor. Buys and sells salvage items."""
from typing import Any, Dict
class Vendor:
    def buy(self, cost: int, salvage: int) -> bool:
        return salvage >= cost
    def sell(self, value: int) -> int:
        return value
