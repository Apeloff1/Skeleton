"""Finite, explicit operator-run native model burn-in contracts."""
from __future__ import annotations
from dataclasses import dataclass
import re

SHA=re.compile(r'^[0-9a-f]{64}$')

class QualificationHeld(RuntimeError):
    """The real native model has not met a bounded observation contract."""


def int_bounds(value, name, low, high):
    if type(value) is not int or not low<=value<=high:
        raise QualificationHeld(f'invalid {name}')
    return value


@dataclass(frozen=True, slots=True)
class BurnInPolicy:
    trials:int=12
    max_output_tokens:int=48
    inference_ms:int=120000
    context_tokens:int=2048
    maximum_p99_ms:int=120000
    maximum_consecutive_faults:int=0
    minimum_generated_tokens:int=1

    def __post_init__(self):
        int_bounds(self.trials,'trial count',1,256)
        int_bounds(self.max_output_tokens,'response ceiling',1,128)
        int_bounds(self.inference_ms,'native timeout',1000,600000)
        int_bounds(self.context_tokens,'native context',128,131072)
        int_bounds(self.maximum_p99_ms,'p99 latency',1000,600000)
        int_bounds(self.maximum_consecutive_faults,'consecutive failures',0,0)
        int_bounds(self.minimum_generated_tokens,'minimum native tokens',0,self.max_output_tokens)

    def record(self)->dict:
        return {'trials':self.trials,'max_output_tokens':self.max_output_tokens,
                'inference_ms':self.inference_ms,'context_tokens':self.context_tokens,
                'maximum_p99_ms':self.maximum_p99_ms,
                'maximum_consecutive_faults':self.maximum_consecutive_faults,
                'minimum_generated_tokens':self.minimum_generated_tokens}
