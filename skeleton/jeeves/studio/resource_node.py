"""Resource node. Harvestable salvage points in rooms."""
from typing import Any, Dict
class ResourceNode:
    def __init__(self, room: int, amount: int = 10):
        self.room = room
        self.amount = amount
        self.harvested = False
    def harvest(self) -> int:
        if self.harvested: return 0
        self.harvested = True
        return self.amount
