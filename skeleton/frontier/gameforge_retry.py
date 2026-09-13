"""Bounded retry policy with deterministic backoff."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class RetryPolicy:
    attempts:int=3
    base_delay:float=0.1
    max_delay:float=2.0
    def __post_init__(self):
        if self.attempts<1 or self.base_delay<0 or self.max_delay<self.base_delay: raise ValueError("invalid retry policy")
    def delay(self, retry_index:int)->float:
        if retry_index<0: raise ValueError("retry_index must be non-negative")
        return min(self.max_delay, self.base_delay*(2**retry_index))
