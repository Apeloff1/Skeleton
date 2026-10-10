"""Self-contained provenance export and offline verification."""
from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Mapping
from .attestation import Attestation
from .commitments import Commitment,canonical_bytes

@dataclass(frozen=True,slots=True)
class PortableBundle:
    semantic_namespace:str
    semantic_kind:str
    semantic_id:str
    semantic_revision:int
    attestation_statement:Mapping[str,object]
    attestation_commitment:Commitment
    def __post_init__(self)->None:
        if not all(isinstance(v,str) and v.strip() for v in (self.semantic_namespace,self.semantic_kind,self.semantic_id)): raise ValueError("semantic identity required")
        if not isinstance(self.semantic_revision,int) or isinstance(self.semantic_revision,bool) or self.semantic_revision<0: raise ValueError("invalid semantic revision")
        actual=Commitment.of(dict(self.attestation_statement),self.attestation_commitment.algorithm)
        if actual!=self.attestation_commitment: raise ValueError("attestation commitment mismatch")
    @property
    def semantic_key(self)->tuple[str,str,str]: return (self.semantic_namespace,self.semantic_kind,self.semantic_id)
    def to_dict(self)->dict[str,object]:
        return {"schema":"skeleton.ai.portable-provenance-bundle.v1","semantic":{"namespace":self.semantic_namespace,"kind":self.semantic_kind,"id":self.semantic_id,"revision":self.semantic_revision},"statement":dict(self.attestation_statement),"commitment":self.attestation_commitment.to_dict()}
    def export_bytes(self)->bytes: return canonical_bytes(self.to_dict())

def from_attestation(attestation:Attestation,*,namespace:str,kind:str,stable_id:str,revision:int=0)->PortableBundle:
    statement=attestation.statement_dict()
    return PortableBundle(namespace,kind,stable_id,revision,statement,attestation.commitment)

def verify_export(payload:bytes)->bool:
    try:
        raw=json.loads(payload.decode("utf-8"))
        if raw.get("schema")!="skeleton.ai.portable-provenance-bundle.v1": return False
        semantic=raw["semantic"]; c=raw["commitment"]
        commitment=Commitment(c["algorithm"],c["value"],c["profile"])
        PortableBundle(semantic["namespace"],semantic["kind"],semantic["id"],semantic["revision"],raw["statement"],commitment)
        return payload==canonical_bytes(raw)
    except (ValueError,TypeError,KeyError,UnicodeDecodeError,json.JSONDecodeError):
        return False

def same_semantic_lineage(a:PortableBundle,b:PortableBundle)->bool:
    return a.semantic_key==b.semantic_key and b.semantic_revision>=a.semantic_revision

__all__=["PortableBundle","from_attestation","same_semantic_lineage","verify_export"]
