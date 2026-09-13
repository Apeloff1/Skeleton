"""Fail-closed invariant checks with a stable exception type."""

class InvariantViolation(ValueError):
    """Raised when a frontier contract invariant is violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InvariantViolation(message)
