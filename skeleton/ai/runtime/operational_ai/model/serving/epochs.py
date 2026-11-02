"""Versioned model swap records preserving explicit old and new identities."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import ModelIdentity,ServingError

@dataclass(frozen=True,slots=True)
class Promotion:
    prior:ModelIdentity
    successor:ModelIdentity
    approved:bool
    evidence_digest:str

    def allowed(self)->bool:
        return (self.approved is True and len(self.evidence_digest)==64 and
            self.prior.epoch+1==self.successor.epoch)


def require_promotion(p:Promotion,active:ModelIdentity)->ModelIdentity:
    if not isinstance(p,Promotion) or not p.allowed() or p.prior!=active:
        raise ServingError('model promotion lacks ordered independent approval')
    return p.successor
