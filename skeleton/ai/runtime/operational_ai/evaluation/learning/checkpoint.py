"""Checkpoint chain continuity with strict parent identity and bounded epochs."""
from __future__ import annotations
from dataclasses import dataclass
from .dataset import LearningError
import re

@dataclass(frozen=True,slots=True)
class Checkpoint:
    step:int
    epoch:int
    bytes:int
    sha256:str
    parent_sha256:str
    optimizer_sha256:str

    def __post_init__(self):
        if any(type(x) is not int or x<0 for x in (self.step,self.epoch,self.bytes)):
            raise LearningError('checkpoint counters must be finite nonnegative ints')
        if self.bytes>2_000_000_000:raise LearningError('checkpoint exceeds 2GB upload limit')
        for name in ('sha256','parent_sha256','optimizer_sha256'):
            if not re.fullmatch(r'[0-9a-f]{64}',getattr(self,name)):
                raise LearningError('invalid checkpoint SHA')


def verify_chain(chain:tuple[Checkpoint,...],*,base_sha:str)->bool:
    if not chain:return False
    prior=base_sha;step=-1;epoch=-1
    for checkpoint in chain:
        if checkpoint.parent_sha256!=prior or checkpoint.step<=step or checkpoint.epoch<epoch:
            return False
        prior=checkpoint.sha256;step=checkpoint.step;epoch=checkpoint.epoch
    return True
