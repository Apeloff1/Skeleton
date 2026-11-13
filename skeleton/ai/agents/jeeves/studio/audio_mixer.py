"""Audio mixer. Bus volumes for sfx music ui."""
from typing import Any, Dict
class AudioMixer:
    def __init__(self):
        self.buses = {"sfx": 0.8, "music": 0.6, "ui": 0.7}
    def set(self, bus: str, vol: float) -> None:
        if bus in self.buses: self.buses[bus] = max(0.0, min(1.0, vol))
    def status(self) -> Dict[str, float]:
        return dict(self.buses)
