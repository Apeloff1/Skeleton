"""Archival bundles and predecessor-linked re-attestation."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Final
from .attestation import Attestation
from .commitments import Commitment
from .crypto_inventory import select_for_issuance

ARCHIVE_SCHEMA: Final="skeleton.ai.provenance-archive.v1"

@dataclass(frozen=True,slots=True)
class ArchiveGeneration:
    statement:Commitment
    predecessor:Commitment|None
    generation:int
    issued_year:int
    reason:str
    def __post_init__(self)->None:
        if self.generation<0: raise ValueError("generation must be non-negative")
        if self.generation==0 and self.predecessor is not None: raise ValueError("genesis archive cannot have predecessor")
        if self.generation>0 and self.predecessor is None: raise ValueError("re-attestation requires predecessor")
        if not self.reason.strip(): raise ValueError("archive reason required")
    def identity_dict(self)->dict[str,object]:
        return {"schema":ARCHIVE_SCHEMA,"statement":self.statement.to_dict(),"predecessor":None if self.predecessor is None else self.predecessor.to_dict(),"generation":self.generation,"issued_year":self.issued_year,"reason":self.reason}
    @property
    def archive_commitment(self)->Commitment: return Commitment.of(self.identity_dict())

def genesis(attestation:Attestation,*,year:int)->ArchiveGeneration:
    primitive=select_for_issuance(year)
    statement=Commitment.of(attestation.statement_dict(),primitive.algorithm)
    return ArchiveGeneration(statement,None,0,year,"initial archival commitment")

def reattest(previous:ArchiveGeneration,attestation:Attestation,*,year:int,reason:str)->ArchiveGeneration:
    primitive=select_for_issuance(year)
    statement=Commitment.of(attestation.statement_dict(),primitive.algorithm)
    # Algorithm changes may alter commitment value, so semantic equality is
    # verified from the authoritative statement before a new generation issues.
    if attestation.commitment.value != Commitment.of(attestation.statement_dict()).value:
        raise ValueError("attestation semantic verification failed")
    return ArchiveGeneration(statement,previous.archive_commitment,previous.generation+1,year,reason)

def verify_archive_chain(generations:tuple[ArchiveGeneration,...])->bool:
    if not generations or generations[0].generation!=0 or generations[0].predecessor is not None: return False
    for index,(prev,current) in enumerate(zip(generations,generations[1:]),start=1):
        if current.generation!=index: return False
        if current.predecessor!=prev.archive_commitment: return False
    return True

__all__=["ARCHIVE_SCHEMA","ArchiveGeneration","genesis","reattest","verify_archive_chain"]
