"""Door. Locked or open based on key or optical."""
from typing import Any, Dict
class Door:
    def __init__(self, locked: bool = False):
        self.locked = locked
    def open(self, has_key: bool = False, optical: float = 0.9) -> bool:
        if not self.locked or has_key or optical > 0.95:
            self.locked = False
            return True
        return False
