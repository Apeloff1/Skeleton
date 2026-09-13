"""Typed outcome contract separating success from explicit failure."""
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Outcome(Generic[T]):
    value: Optional[T] = None
    error: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.error is None):
            raise ValueError("outcome must contain exactly one of value or error")

    @property
    def ok(self) -> bool:
        return self.error is None
