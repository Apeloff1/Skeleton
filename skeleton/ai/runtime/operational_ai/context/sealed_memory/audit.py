"""Read-only encrypted-memory integrity scan and source-count inventory."""
from __future__ import annotations
from dataclasses import dataclass
from .store import SealedMemoryStore
from ..sources import Source
from ...authority.identity import Actor
from .keys import MemoryKeyError

@dataclass(frozen=True,slots=True)
class SealedMemoryAudit:
    state:str
    checked:int
    errors:tuple[str,...]


def audit(store:SealedMemoryStore,actor:Actor,*,maximum:int=2048)->SealedMemoryAudit:
    try:
        sources=store.sources(actor,maximum=maximum)
        return SealedMemoryAudit('authenticated',len(sources),())
    except MemoryKeyError as exc:
        return SealedMemoryAudit('blocked',0,(str(exc),))
