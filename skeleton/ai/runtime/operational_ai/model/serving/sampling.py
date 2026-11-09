"""Deterministic seed and sampling parameter admission."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import math
from .contracts import ServingError

@dataclass(frozen=True,slots=True)
class Sampling:
    temperature:float
    seed:int
    max_new_tokens:int
    top_p:float=1.0

    def __post_init__(self):
        if (type(self.temperature) not in (float,int) or not math.isfinite(self.temperature)
            or not 0<self.temperature<=2 or type(self.seed) is not int
            or not 0<=self.seed<2**32 or type(self.max_new_tokens) is not int
            or not 1<=self.max_new_tokens<=4096 or type(self.top_p) not in (float,int)
            or not math.isfinite(self.top_p) or not 0<self.top_p<=1):
            raise ServingError('invalid sampling configuration')

    def child_seed(self,step:int)->int:
        if type(step) is not int or not 0<=step<2**32:
            raise ServingError('invalid child step')
        raw=self.seed.to_bytes(4,'big')+step.to_bytes(4,'big')
        return int.from_bytes(sha256(raw).digest()[:4],'big')
