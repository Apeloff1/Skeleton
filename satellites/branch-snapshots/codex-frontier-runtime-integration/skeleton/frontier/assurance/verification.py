"""Verification record for promotion and integration gates."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Verification:
    artifact: str
    passed: bool
    checks: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.artifact.strip():
            raise ValueError("artifact must not be empty")
        if any(not check.strip() for check in self.checks):
            raise ValueError("verification checks must be named")

    def require(self) -> None:
        if not self.passed:
            raise RuntimeError(f"verification failed: {self.artifact}")
