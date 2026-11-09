from __future__ import annotations
from skeleton.ai.model_runtime.runtime_contracts import ReplayReceipt
from skeleton.ai.runtime.provenance.admission import admit_execution
from skeleton.ai.runtime.provenance.crypto_backends import Ed25519Keypair,verifier_from_public_bytes
from skeleton.ai.runtime.provenance.key_lifecycle import KeyRecord,KeyRegistry
from skeleton.ai.runtime.provenance.quorum import QuorumPolicy
from skeleton.ai.runtime.provenance.runtime_bridge import attestation_from_replay
from skeleton.ai.runtime.provenance.signature_capabilities import SignerRegistry
from skeleton.ai.runtime.provenance.signed_envelope import SignaturePolicy,sign_envelope
from skeleton.ai.runtime.provenance.trust_policy import TrustPolicy

def _att():
    r=ReplayReceipt("a"*64,"b"*64,"c"*64,"d"*64,"e"*64,"f"*64,"1"*64,3)
    return attestation_from_replay(r,context_digest="2"*64,admission_policy_digest="3"*64)

def test_real_ed25519_round_trip_and_wrong_payload_rejection() -> None:
    key=Ed25519Keypair.generate(); sig=key.sign(b"payload")
    assert key.verify(b"payload",sig)
    assert not key.verify(b"other",sig)
    assert verifier_from_public_bytes(key.public_bytes())(b"payload",sig)

def test_revocation_preserves_pre_revocation_historical_signature() -> None:
    record=KeyRecord("k","ed25519",100,revoked_at=200,revocation_reason="rotation")
    assert record.valid_for_historical_verification(199)
    assert not record.valid_for_historical_verification(200)
    assert not record.valid_for_issuance(201)

def test_admission_accepts_real_key_with_bound_provenance() -> None:
    att=_att(); key=Ed25519Keypair.generate()
    signers=SignerRegistry(); signers.register("ed25519",key.sign)
    env=sign_envelope(att.statement_dict(),(("ed25519",key.key_id),),signers)
    keys=KeyRegistry(); keys.register(KeyRecord(key.key_id,"ed25519",100))
    verifiers={("ed25519",key.key_id):verifier_from_public_bytes(key.public_bytes())}
    decision=admit_execution(att,env,verifiers,signed_at=150,keys=keys,trust_policy=TrustPolicy(),quorum_policy=QuorumPolicy())
    assert decision.admitted and decision.valid_signature_count==1

def test_admission_rejects_signature_after_key_revocation() -> None:
    att=_att(); key=Ed25519Keypair.generate()
    signers=SignerRegistry(); signers.register("ed25519",key.sign)
    env=sign_envelope(att.statement_dict(),(("ed25519",key.key_id),),signers)
    keys=KeyRegistry(); keys.register(KeyRecord(key.key_id,"ed25519",100,revoked_at=200,revocation_reason="compromise"))
    verifiers={("ed25519",key.key_id):verifier_from_public_bytes(key.public_bytes())}
    decision=admit_execution(att,env,verifiers,signed_at=200,keys=keys,trust_policy=TrustPolicy(),quorum_policy=QuorumPolicy())
    assert not decision.admitted and "signature-quorum-failed" in decision.reasons

def test_quorum_requires_key_diversity() -> None:
    att=_att(); key=Ed25519Keypair.generate()
    signers=SignerRegistry(); signers.register("ed25519",key.sign)
    env=sign_envelope(att.statement_dict(),(("ed25519",key.key_id),),signers)
    keys=KeyRegistry(); keys.register(KeyRecord(key.key_id,"ed25519",100))
    decision=admit_execution(att,env,{("ed25519",key.key_id):key.verify},signed_at=150,keys=keys,trust_policy=TrustPolicy(),quorum_policy=QuorumPolicy(minimum_valid=1,minimum_distinct_keys=2))
    assert not decision.admitted
