"""Wave spawner. Sequential enemy waves."""
from typing import Any, Dict, List
class WaveSpawner:
    def __init__(self, waves: List[int]):
        self.waves = waves
        self.current = 0
    def next_wave(self) -> int:
        if self.current >= len(self.waves): return 0
        count = self.waves[self.current]
        self.current += 1
        return count
