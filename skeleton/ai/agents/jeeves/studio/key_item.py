"""Key item. Unlocks doors or endings."""
from typing import Any, Dict
class KeyItem:
    def __init__(self, name: str):
        self.name = name
        self.held = False
    def pickup(self) -> None:
        self.held = True
