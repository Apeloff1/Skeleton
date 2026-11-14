"""Duration and deadline arithmetic without floating point timestamp ambiguity."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import require_int
from .errors import deny


@dataclass(frozen=True, slots=True)
class Deadline:
    admitted_ms:int
    expires_ms:int

    def __post_init__(self):
        require_int(self.admitted_ms,0,2**63-1,"deadline-admitted")
        require_int(self.expires_ms,0,2**63-1,"deadline-expires")
        if not self.admitted_ms<self.expires_ms<=self.admitted_ms+3600000:
            deny("deadline-window")

    def remaining(self,now_ms:int)->int:
        require_int(now_ms,0,2**63-1,"deadline-clock")
        return max(0,self.expires_ms-now_ms)

    def require_active(self,now_ms:int)->None:
        if not self.admitted_ms<=now_ms<self.expires_ms:
            deny("deadline-expired")

    def child(self,*,now_ms:int,duration_ms:int)->"Deadline":
        self.require_active(now_ms)
        require_int(duration_ms,1,3600000,"deadline-child")
        return Deadline(now_ms,min(self.expires_ms,now_ms+duration_ms))
