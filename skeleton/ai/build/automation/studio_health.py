"""Compact health snapshot for autonomous completion."""
from __future__ import annotations
from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class StudioHealth:
    queued:int; active:int; accepted:int; rejected:int; quarantined:int; validation_failures:int
    def __post_init__(self):
        if any(v<0 for v in asdict(self).values()): raise ValueError("health counters cannot be negative")
    @property
    def healthy(self)->bool:
        return self.quarantined==0 and self.validation_failures==0
