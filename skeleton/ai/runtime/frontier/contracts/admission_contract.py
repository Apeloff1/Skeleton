"""Stable admission evidence; not a standalone authorization token."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdmissionContract:
    request_id: str
    accepted: bool
    reason: str

    def __post_init__(self) -> None:
        if type(self.request_id) is not str or not self.request_id.strip() or len(self.request_id) > 256:
            raise ValueError("invalid request identity")
        if type(self.accepted) is not bool:
            raise ValueError("admission requires an explicit boolean")
        if type(self.reason) is not str or not self.reason.strip() or len(self.reason) > 1024:
            raise ValueError("invalid admission reason")
