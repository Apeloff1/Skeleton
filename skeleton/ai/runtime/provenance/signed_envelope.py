"""Signed provenance envelopes with hybrid-signature policy."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable,Mapping
from .commitments import Commitment,canonical_bytes
from .signature_capabilities import CAPABILITIES,SignerRegistry

_PQ={c.algorithm for c in CAPABILITIES if c.post_quantum}
_CLASSICAL={c.algorithm for c in CAPABILITIES if not c.post_quantum}

@dataclass(frozen=True,slots=True)
class Signature:
    algorithm:str
    key_id:str
    signature:bytes
    def __post_init__(self)->None:
        if not self.key_id.strip() or not self.signature: raise ValueError("signature and key identity required")
        if self.algorithm not in _PQ|_CLASSICAL: raise ValueError("unknown signature algorithm")
    def to_dict(self)->dict[str,str]:
        import base64
        return {"algorithm":self.algorithm,"key_id":self.key_id,"signature":base64.b64encode(self.signature).decode("ascii")}

@dataclass(frozen=True,slots=True)
class SignaturePolicy:
    require_classical:bool=True
    require_post_quantum:bool=False
    minimum_signatures:int=1
    def __post_init__(self)->None:
        if self.minimum_signatures<1: raise ValueError("minimum signatures must be positive")

@dataclass(frozen=True,slots=True)
class SignedEnvelope:
    payload:Mapping[str,object]
    signatures:tuple[Signature,...]
    def __post_init__(self)->None:
        canonical_bytes(dict(self.payload))
        sigs=tuple(self.signatures)
        ids=[(s.algorithm,s.key_id) for s in sigs]
        if len(ids)!=len(set(ids)): raise ValueError("duplicate signing identity")
        object.__setattr__(self,"signatures",sigs)
    @property
    def payload_commitment(self)->Commitment: return Commitment.of(dict(self.payload))

Verifier=Callable[[bytes,bytes],bool]

def sign_envelope(payload:Mapping[str,object],requests:tuple[tuple[str,str],...],registry:SignerRegistry)->SignedEnvelope:
    body=canonical_bytes(dict(payload))
    signatures=tuple(Signature(algorithm,key_id,registry.sign(algorithm,body)) for algorithm,key_id in requests)
    return SignedEnvelope(payload,signatures)

def verify_envelope(envelope:SignedEnvelope,verifiers:Mapping[tuple[str,str],Verifier],policy:SignaturePolicy)->bool:
    body=canonical_bytes(dict(envelope.payload))
    valid:list[Signature]=[]
    for signature in envelope.signatures:
        verifier=verifiers.get((signature.algorithm,signature.key_id))
        if verifier is None: continue
        try:
            if verifier(body,signature.signature): valid.append(signature)
        except Exception:
            continue
    if len(valid)<policy.minimum_signatures: return False
    if policy.require_classical and not any(s.algorithm in _CLASSICAL for s in valid): return False
    if policy.require_post_quantum and not any(s.algorithm in _PQ for s in valid): return False
    return True

__all__=["Signature","SignaturePolicy","SignedEnvelope","sign_envelope","verify_envelope"]
