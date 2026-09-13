"""Stable admission contract for frontier runtime composition."""
from dataclasses import dataclass

@dataclass(frozen=True)
class AdmissionContract:
    request_id: str
    accepted: bool
    reason: str
