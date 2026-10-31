"""Switch. Toggles doors or hazards."""
from typing import Any, Dict
class Switch:
    def __init__(self):
        self.on = False
    def toggle(self) -> bool:
        self.on = not self.on
        return self.on
