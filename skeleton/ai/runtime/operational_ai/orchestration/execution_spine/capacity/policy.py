"""Explicit deployment policy for context inclusion and tokenizer qualification."""
from __future__ import annotations
from dataclasses import dataclass
from ..contracts import SpineError
from .contracts import CapacityPolicy


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    source_candidates: int
    require_native_tokenizer: bool
    trials: int

    def __post_init__(self):
        if self.name not in ('portable','strict','diagnostic'):
            raise SpineError('unknown context admission deployment profile')
        if type(self.source_candidates) is not int or not 1 <= self.source_candidates <= 128:
            raise SpineError('invalid context source admission profile')
        if type(self.require_native_tokenizer) is not bool:
            raise SpineError('invalid native tokenizer policy')
        if type(self.trials) is not int or not 1 <= self.trials <= 8192:
            raise SpineError('invalid context planner trial profile')

    def policy(self) -> CapacityPolicy:
        return CapacityPolicy(self.source_candidates,self.trials,self.require_native_tokenizer)


PROFILES = {
    'portable': Profile('portable',32,False,512),
    'strict': Profile('strict',32,True,512),
    'diagnostic': Profile('diagnostic',128,False,8192),
}


def named(name: str) -> CapacityPolicy:
    if type(name) is not str or name not in PROFILES:
        raise SpineError('unsupported context admission profile')
    return PROFILES[name].policy()
