"""Conservative native context admission with explicit reserve."""
from __future__ import annotations
from .contracts import ServingError


def admit_window(prompt_tokens:int,output_tokens:int,context_ceiling:int,reserved_tokens:int=32)->int:
    for n in (prompt_tokens,output_tokens,context_ceiling,reserved_tokens):
        if type(n) is not int or n<0:raise ServingError('context admission requires nonnegative integers')
    if output_tokens<=0 or prompt_tokens+output_tokens+reserved_tokens>context_ceiling:
        raise ServingError('native context capacity exceeded')
    return context_ceiling-(prompt_tokens+output_tokens+reserved_tokens)
