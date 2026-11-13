"""Context budget reserves space for output and structural boundaries."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import ContextError

@dataclass(frozen=True,slots=True)
class Window:
    ceiling:int
    output_reserved:int
    structural_reserved:int=32

    def __post_init__(self):
        if (any(type(v) is not int or v<0 for v in (self.ceiling,self.output_reserved,self.structural_reserved))
            or self.ceiling<128 or self.output_reserved<=0 or
            self.output_reserved+self.structural_reserved>=self.ceiling):
            raise ContextError('invalid native context window')

    @property
    def input_ceiling(self)->int:
        return self.ceiling-self.output_reserved-self.structural_reserved
