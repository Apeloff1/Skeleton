"""Bounded manual-recovery retry schedule; not an autonomous inference retry."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import require_int
from .errors import deny


@dataclass(frozen=True, slots=True)
class ManualRetrySchedule:
    first_delay_ms:int=1000
    max_delay_ms:int=60000
    max_attempts:int=5

    def __post_init__(self):
        require_int(self.first_delay_ms,100,60000,"backoff-first")
        require_int(self.max_delay_ms,self.first_delay_ms,3600000,"backoff-max")
        require_int(self.max_attempts,1,20,"backoff-attempts")

    def next_delay(self,attempt:int,*,operator_approved:bool,
                   authoritative_no_commit_proved:bool)->int:
        require_int(attempt,1,self.max_attempts,"backoff-attempt")
        if operator_approved is not True or authoritative_no_commit_proved is not True:
            deny("backoff-operator-proof")
        return min(self.max_delay_ms,self.first_delay_ms*(2**(attempt-1)))
