"""Portable, offline-verifiable AI execution attestations.

The statement is authoritative. Witnesses only attest observation of its digest;
they are not storage for the statement itself.
"""
from __future__ import annotations
from dataclasses import dataclass,field
from typing import Mapping,Final
from .commitments import Commitment,canonical_bytes

SCHEMA: Final="skeleton.ai.execution-attestation.v1"
PREDICATE_TYPE: Final="skeleton.ai/execution/v1"

@dataclass(frozen=True,slots=True)
class Subject:
    name:str
    commitment:Commitment
    def __post_init__(self)->None:
        if not self.name.strip(): raise ValueError("subject name required")
    def to_dict(self)->dict[str,object]: return {"name":self.name,"commitment":self.commitment.to_dict()}

@dataclass(frozen=True,slots=True)
class Witness:
    kind:str
    authority:str
    statement:Commitment
    observed_at:str|None=None
    def __post_init__(self)->None:
        if not self.kind.strip() or not self.authority.strip(): raise ValueError("witness identity required")
    def to_dict(self)->dict[str,object]:
        return {"kind":self.kind,"authority":self.authority,"statement":self.statement.to_dict(),"observed_at":self.observed_at}

@dataclass(frozen=True,slots=True)
class Attestation:
    subjects:tuple[Subject,...]
    predicate:Mapping[str,object]
    witnesses:tuple[Witness,...]=field(default_factory=tuple)
    schema:str=SCHEMA
    predicate_type:str=PREDICATE_TYPE
    def __post_init__(self)->None:
        if self.schema!=SCHEMA or self.predicate_type!=PREDICATE_TYPE: raise ValueError("unsupported attestation contract")
        subjects=tuple(self.subjects)
        if not subjects: raise ValueError("at least one subject required")
        names=[s.name for s in subjects]
        if len(names)!=len(set(names)): raise ValueError("subject names must be unique")
        witnesses=tuple(self.witnesses)
        authorities=[(w.kind,w.authority) for w in witnesses]
        if len(authorities)!=len(set(authorities)): raise ValueError("witness authorities must be unique per kind")
        object.__setattr__(self,"subjects",subjects); object.__setattr__(self,"witnesses",witnesses)
        canonical_bytes(dict(self.predicate))
    def statement_dict(self)->dict[str,object]:
        return {"schema":self.schema,"predicate_type":self.predicate_type,"subjects":[s.to_dict() for s in sorted(self.subjects,key=lambda s:s.name)],"predicate":dict(self.predicate)}
    @property
    def commitment(self)->Commitment: return Commitment.of(self.statement_dict())
    def verify_offline(self)->bool:
        target=self.commitment
        return all(w.statement==target for w in self.witnesses)
    def with_witness(self,kind:str,authority:str,observed_at:str|None=None)->"Attestation":
        witness=Witness(kind,authority,self.commitment,observed_at)
        return Attestation(self.subjects,self.predicate,self.witnesses+(witness,),self.schema,self.predicate_type)

__all__=["Attestation","PREDICATE_TYPE","SCHEMA","Subject","Witness"]
