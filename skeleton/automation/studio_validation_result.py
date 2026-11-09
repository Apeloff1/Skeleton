"""Normalized validation outcomes suitable for campaign attribution."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class ValidationResult:
    command:tuple[str,...]; passed:bool; exit_code:int|None; timed_out:bool; output_tail:str
    def __post_init__(self):
        if self.timed_out and self.passed: raise ValueError("timed-out validation cannot pass")
        if len(self.output_tail)>12_000: raise ValueError("validation output exceeds bound")
