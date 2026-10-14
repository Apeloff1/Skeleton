from __future__ import annotations
from skeleton.ai.model_runtime.runtime_contracts import ReplayReceipt
from skeleton.ai.runtime.provenance.runtime_bridge import attestation_from_replay
from skeleton.ai.runtime.provenance.signature_capabilities import SignerRegistry
from skeleton.ai.runtime.provenance.signed_envelope import SignaturePolicy,sign_envelope
from skeleton.ai.runtime.provenance.trust_policy import TrustPolicy,evaluate

def _receipt()->ReplayReceipt: return ReplayReceipt("a"*64,"b"*64,"c"*64,"d"*64,"e"*64,"f"*64,"1"*64,1)

def _signed(att):
    registry=SignerRegistry(); registry.register("ed25519",lambda body:b"s:"+body)
    env=sign_envelope(att.statement_dict(),(("ed25519","key"),),registry)
    return env,{("ed25519","key"):lambda body,sig:sig==b"s:"+body}

def test_trust_policy_accepts_bound_signed_execution() -> None:
    att=attestation_from_replay(_receipt(),context_digest="2"*64,admission_policy_digest="3"*64)
    env,verifiers=_signed(att)
    decision=evaluate(att,env,verifiers,TrustPolicy())
    assert decision.accepted and not decision.reasons

def test_trust_policy_explains_missing_context_and_policy() -> None:
    att=attestation_from_replay(_receipt())
    env,verifiers=_signed(att)
    decision=evaluate(att,env,verifiers,TrustPolicy())
    assert not decision.accepted
    assert {"context-binding-missing","admission-policy-binding-missing"} <= set(decision.reasons)

def test_trust_policy_rejects_envelope_for_different_statement() -> None:
    att=attestation_from_replay(_receipt(),context_digest="2"*64,admission_policy_digest="3"*64)
    registry=SignerRegistry(); registry.register("ed25519",lambda body:b"s:"+body)
    env=sign_envelope({"different":True},(("ed25519","key"),),registry)
    decision=evaluate(att,env,{("ed25519","key"):lambda body,sig:sig==b"s:"+body},TrustPolicy())
    assert not decision.accepted and "envelope-statement-mismatch" in decision.reasons
