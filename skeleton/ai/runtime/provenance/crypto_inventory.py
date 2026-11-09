"""Cryptographic inventory and lifecycle policy for provenance issuance."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Final
from .commitments import ALGORITHMS

@dataclass(frozen=True,slots=True)
class CryptoPrimitive:
    primitive_id:str
    algorithm:str
    purpose:str
    issue_from:int
    issue_until:int|None=None
    verify_until:int|None=None
    def __post_init__(self)->None:
        if self.algorithm not in ALGORITHMS: raise ValueError("unknown algorithm")
        if not self.primitive_id.strip() or not self.purpose.strip(): raise ValueError("primitive identity required")
        if self.issue_from<2020: raise ValueError("unsupported lifecycle start")
        if self.issue_until is not None and self.issue_until<self.issue_from: raise ValueError("invalid issuance window")
        if self.verify_until is not None and self.issue_until is not None and self.verify_until<self.issue_until: raise ValueError("verification retires before issuance")
    def can_issue(self,year:int)->bool: return year>=self.issue_from and (self.issue_until is None or year<=self.issue_until)
    def can_verify(self,year:int)->bool: return year>=self.issue_from and (self.verify_until is None or year<=self.verify_until)
    def to_dict(self)->dict[str,object]:
        return {"primitive_id":self.primitive_id,"algorithm":self.algorithm,"purpose":self.purpose,"issue_from":self.issue_from,"issue_until":self.issue_until,"verify_until":self.verify_until}

INVENTORY: Final=(
    CryptoPrimitive("provenance.sha256","sha256","baseline provenance commitments",2020),
    CryptoPrimitive("provenance.sha3-256","sha3-256","independent provenance commitments",2020),
    CryptoPrimitive("provenance.blake2b-256","blake2b-256","independent provenance commitments",2020),
)

def inventory_manifest()->dict[str,object]:
    ids=[p.primitive_id for p in INVENTORY]
    if len(ids)!=len(set(ids)): raise RuntimeError("duplicate crypto inventory identity")
    return {"schema":"skeleton.ai.crypto-inventory.v1","primitives":[p.to_dict() for p in INVENTORY]}

def select_for_issuance(year:int,preferred:tuple[str,...]=ALGORITHMS)->CryptoPrimitive:
    for algorithm in preferred:
        for primitive in INVENTORY:
            if primitive.algorithm==algorithm and primitive.can_issue(year): return primitive
    raise ValueError("no approved digest primitive available for issuance")

__all__=["CryptoPrimitive","INVENTORY","inventory_manifest","select_for_issuance"]
