"""Normalized terminal outcome for bounded runtime accounting."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ExecutionOutcomeV2:
    request_id: str
    success: bool
    terminal: bool = True
    reason: str = ""

    def __post_init__(self):
        if not self.request_id:
            raise ValueError("request_id is required")

    @property
    def recoverable(self):
        return not self.success and not self.terminal
