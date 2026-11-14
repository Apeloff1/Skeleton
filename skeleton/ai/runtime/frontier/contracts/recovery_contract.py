"""Recovery evidence with bounded retry semantics."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecoveryContract:
    request_id: str
    attempts: int
    recovered: bool

    def __post_init__(self) -> None:
        if type(self.request_id) is not str or not self.request_id.strip() or len(self.request_id) > 256:
            raise ValueError("invalid request identity")
        if type(self.attempts) is not int or not 0 <= self.attempts <= 1000:
            raise ValueError("invalid retry count")
        if type(self.recovered) is not bool:
            raise ValueError("recovery requires an explicit boolean")
