from __future__ import annotations
from skeleton.ai.model_runtime.runtime_contracts import ReplayReceipt
from skeleton.ai.runtime.provenance.runtime_bridge import attestation_from_replay,verify_replay_binding
from skeleton.ai.runtime.provenance.signature_capabilities import SignerRegistry
from skeleton.ai.runtime.provenance.signed_envelope import SignaturePolicy,sign_envelope,verify_envelope

def _receipt()->ReplayReceipt:
    return ReplayReceipt("a"*64,"b"*64,"c"*64,"d"*64,"e"*64,"f"*64,"1"*64,7)

def test_native_replay_becomes_portable_attestation() -> None:
    receipt=_receipt()
    att=attestation_from_replay(receipt,context_digest="2"*64,admission_policy_digest="3"*64)
    assert verify_replay_binding(att,receipt)
    assert {s.name for s in att.subjects}=={"native-runtime-receipt","model","tokenizer","output"}

def test_runtime_bridge_rejects_reserved_predicate_override() -> None:
    try:
        attestation_from_replay(_receipt(),extra={"request_digest":"wrong"})
    except ValueError as exc:
        assert "reserved" in str(exc)
    else:
        raise AssertionError("reserved runtime field substitution accepted")

def test_hybrid_policy_requires_independent_classical_and_pq_signatures() -> None:
    registry=SignerRegistry()
    registry.register("ed25519",lambda payload:b"classical:"+payload)
    registry.register("ml-dsa-65",lambda payload:b"pq:"+payload)
    payload={"statement":"x"}
    envelope=sign_envelope(payload,(("ed25519","key-c"),("ml-dsa-65","key-pq")),registry)
    verifiers={
        ("ed25519","key-c"):lambda body,sig:sig==b"classical:"+body,
        ("ml-dsa-65","key-pq"):lambda body,sig:sig==b"pq:"+body,
    }
    assert verify_envelope(envelope,verifiers,SignaturePolicy(True,True,2))

def test_hybrid_policy_rejects_missing_pq_verifier() -> None:
    registry=SignerRegistry(); registry.register("ed25519",lambda payload:b"c:"+payload); registry.register("ml-dsa-65",lambda payload:b"p:"+payload)
    envelope=sign_envelope({"x":1},(("ed25519","c"),("ml-dsa-65","p")),registry)
    verifiers={("ed25519","c"):lambda body,sig:sig==b"c:"+body}
    assert not verify_envelope(envelope,verifiers,SignaturePolicy(True,True,2))

def test_wrong_key_identity_cannot_validate_signature() -> None:
    registry=SignerRegistry(); registry.register("ed25519",lambda payload:b"sig:"+payload)
    envelope=sign_envelope({"x":1},(("ed25519","correct"),),registry)
    verifiers={("ed25519","wrong"):lambda body,sig:True}
    assert not verify_envelope(envelope,verifiers,SignaturePolicy())

def test_verifier_exception_fails_closed() -> None:
    registry=SignerRegistry(); registry.register("ed25519",lambda payload:b"sig")
    envelope=sign_envelope({"x":1},(("ed25519","k"),),registry)
    def broken(body:bytes,sig:bytes)->bool: raise RuntimeError("backend down")
    assert not verify_envelope(envelope,{("ed25519","k"):broken},SignaturePolicy())
