"""Fail-closed runtime admission from provenance trust evidence."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
from .attestation import Attestation
from .key_lifecycle import KeyRegistry
from .quorum import QuorumPolicy,quorum_satisfied
from .signed_envelope import SignedEnvelope,Signature,Verifier
from .trust_policy import TrustDecision,TrustPolicy,evaluate
from .commitments import canonical_bytes

@dataclass(frozen=True,slots=True)
class AdmissionDecision:
    admitted:bool
    reasons:tuple[str,...]
    valid_signature_count:int

def admit_execution(
    attestation:Attestation,
    envelope:SignedEnvelope,
    verifiers:Mapping[tuple[str,str],Verifier],
    *,
    signed_at:int,
    keys:KeyRegistry,
    trust_policy:TrustPolicy,
    quorum_policy:QuorumPolicy,
)->AdmissionDecision:
    body=canonical_bytes(dict(envelope.payload))
    valid:list[Signature]=[]
    for signature in envelope.signatures:
        verifier=verifiers.get((signature.algorithm,signature.key_id))
        if verifier is None: continue
        try:
            if not keys.eligible(signature.key_id,signature.algorithm,signed_at): continue
            if verifier(body,signature.signature): valid.append(signature)
        except (ValueError,RuntimeError):
            continue
    trust=evaluate(attestation,envelope,verifiers,trust_policy)
    reasons=list(trust.reasons)
    if not quorum_satisfied(tuple(valid),quorum_policy): reasons.append("signature-quorum-failed")
    return AdmissionDecision(not reasons,tuple(dict.fromkeys(reasons)),len(valid))

__all__=["AdmissionDecision","admit_execution"]
