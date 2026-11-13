"""Conservative context-space reservations for prompt and output usage."""
from __future__ import annotations
from dataclasses import dataclass
from .manifest import GGUFManifestError

@dataclass(frozen=True,slots=True)
class TokenReservation:
    model_context:int
    prompt_ceiling:int
    generation_ceiling:int
    reserve:int


def reserve_context(*,context:int,prompt_tokens:int,output_tokens:int,
                    safety_margin:int=32)->TokenReservation:
    for x in (context,prompt_tokens,output_tokens,safety_margin):
        if type(x) is not int or x<0:raise GGUFManifestError('invalid token reservation')
    if not 128<=context<=131072 or not 1<=output_tokens<=4096:
        raise GGUFManifestError('token limits outside execution contract')
    if prompt_tokens+output_tokens+safety_margin>context:
        raise GGUFManifestError('model context overflow; no hidden truncation')
    return TokenReservation(context,context-output_tokens-safety_margin,output_tokens,safety_margin)
