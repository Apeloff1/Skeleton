"""Statistics. Lifetime counters."""
from typing import Any, Dict
class Statistics:
    def __init__(self):
        self.counters = {"packs": 0, "bosses": 0, "deaths": 0, "extracts": 0}
    def inc(self, key: str, n: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + n
    def get(self) -> Dict[str, int]:
        return dict(self.counters)
