"""Explicit verification records: empty evidence can never authorize promotion."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Verification:
    artifact: str
    passed: bool
    checks: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.artifact) is not str or not self.artifact.strip() or len(self.artifact) > 1024:
            raise ValueError("invalid artifact")
        if type(self.passed) is not bool:
            raise ValueError("passed must be a boolean")
        if type(self.checks) is not tuple or len(self.checks) > 4096:
            raise ValueError("invalid verification inventory")
        if any(type(check) is not str or not check.strip() or len(check) > 1024 for check in self.checks):
            raise ValueError("verification checks must be named")
        if len(set(self.checks)) != len(self.checks):
            raise ValueError("duplicate verification checks")
        if self.passed and not self.checks:
            raise ValueError("successful verification requires evidence")

    def require(self) -> None:
        if not self.passed:
            raise RuntimeError(f"verification failed: {self.artifact}")
