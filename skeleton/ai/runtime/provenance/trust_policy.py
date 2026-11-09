"""Policy evaluation for provenance trust decisions."""
from __future__ import annotations
from dataclasses import dataclass
from .attestation import Attestation
from .signed_envelope import SignaturePolicy,SignedEnvelope,Verifier,verify_envelope
from typing import Mapping

@dataclass(frozen=True,slots=True)
class TrustPolicy:
    signatures:SignaturePolicy=SignaturePolicy()
    require_context:bool=True
    require_admission_policy:bool=True
    minimum_witnesses:int=0
    allowed_witness_kinds:tuple[str,...]=()
    def __post_init__(self)->None:
        if self.minimum_witnesses<0: raise ValueError("minimum witnesses cannot be negative")

@dataclass(frozen=True,slots=True)
class TrustDecision:
    accepted:bool
    reasons:tuple[str,...]

def evaluate(attestation:Attestation,envelope:SignedEnvelope,verifiers:Mapping[tuple[str,str],Verifier],policy:TrustPolicy)->TrustDecision:
    reasons:list[str]=[]
    if envelope.payload!=attestation.statement_dict(): reasons.append("envelope-statement-mismatch")
    if not verify_envelope(envelope,verifiers,policy.signatures): reasons.append("signature-policy-failed")
    if policy.require_context and not attestation.predicate.get("context_digest"): reasons.append("context-binding-missing")
    if policy.require_admission_policy and not attestation.predicate.get("admission_policy_digest"): reasons.append("admission-policy-binding-missing")
    witnesses=attestation.witnesses
    if policy.allowed_witness_kinds:
        witnesses=tuple(w for w in witnesses if w.kind in set(policy.allowed_witness_kinds))
    if len(witnesses)<policy.minimum_witnesses: reasons.append("witness-threshold-failed")
    if not attestation.verify_offline(): reasons.append("witness-binding-failed")
    return TrustDecision(not reasons,tuple(reasons))

__all__=["TrustDecision","TrustPolicy","evaluate"]
