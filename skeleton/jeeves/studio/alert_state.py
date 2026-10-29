"""Alert state. Idle, suspicious, alerted for enemies."""
from typing import Any, Dict
class AlertState:
    def __init__(self):
        self.state = "idle"
    def update(self, detected: bool, lost: bool) -> str:
        if detected: self.state = "alerted"
        elif lost and self.state == "alerted": self.state = "suspicious"
        elif self.state == "suspicious": self.state = "idle"
        return self.state
