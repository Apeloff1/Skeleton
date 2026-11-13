"""Exact citation validation against scoped source documents."""
from __future__ import annotations
from dataclasses import dataclass
from ..authority.canonical import ContractViolation
from .sources import Source
from .lexical import Hit


def validate_hit(source:Source,hit:Hit)->dict:
    if source.source_id!=hit.source_id or source.digest!=hit.sha256:
        raise ContractViolation("citation identity mismatch")
    if hit.start<0 or hit.end>len(source.body) or hit.end<=hit.start:
        raise ContractViolation("citation offset out of bounds")
    if source.body[hit.start:hit.end]!=hit.body:
        raise ContractViolation("citation passage changed")
    if source.origin!=hit.origin or source.trust!=hit.trust or source.rights!=hit.rights:
        raise ContractViolation("citation authority or provenance drift")
    return {"source_id":source.source_id,"sha256":source.digest,
            "offset_start":hit.start,"offset_end":hit.end,"verified":True,
            "instruction_authority":False}
