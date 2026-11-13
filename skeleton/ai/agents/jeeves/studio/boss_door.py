"""Boss door. Opens after room clears."""
from typing import Any, Dict
class BossDoor:
    def __init__(self):
        self.open = False
    def check(self, rooms_cleared: int, required: int = 5) -> bool:
        self.open = rooms_cleared >= required
        return self.open
