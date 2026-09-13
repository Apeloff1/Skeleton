"""Normalized terminal outcome for bounded runtime accounting."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionOutcomeV2:
    request_id: str
    success: bool
    terminal: bool = True
    reason: str = ""

    def __post_init__(self):
        if not isinstance(self.request_id, str) or not self.request_id:
            raise ValueError("request_id is required")
        if not isinstance(self.success, bool):
            raise TypeError("success must be bool")
        if not isinstance(self.terminal, bool):
            raise TypeError("terminal must be bool")
        if not isinstance(self.reason, str):
            raise TypeError("reason must be str")

    @property
    def recoverable(self):
        return not self.success and not self.terminal
