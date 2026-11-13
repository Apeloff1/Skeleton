"""Trade offer. NPC exchange proposals."""
from typing import Any, Dict
class TradeOffer:
    def __init__(self, give: str, receive: str, cost: int):
        self.give = give
        self.receive = receive
        self.cost = cost
    def accept(self, salvage: int) -> bool:
        return salvage >= self.cost
