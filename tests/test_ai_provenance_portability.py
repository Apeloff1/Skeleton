from __future__ import annotations
import pytest
from skeleton.ai.runtime.provenance.attestation import Attestation,Subject
from skeleton.ai.runtime.provenance.commitments import Commitment
from skeleton.ai.runtime.provenance.portable_bundle import from_attestation,same_semantic_lineage,verify_export
from skeleton.ai.runtime.provenance.signature_capabilities import CAPABILITIES,SignerRegistry,negotiate

def _att()->Attestation:
    return Attestation((Subject("execution",Commitment.of({"request":"r","output":"o"})),),{"runtime":"native"})

def test_portable_bundle_round_trips_offline() -> None:
    bundle=from_attestation(_att(),namespace="skeleton",kind="execution",stable_id="job-1")
    assert verify_export(bundle.export_bytes())

def test_portable_bundle_detects_byte_level_reencoding() -> None:
    payload=from_attestation(_att(),namespace="skeleton",kind="execution",stable_id="job-1").export_bytes()
    assert not verify_export(payload+b" ")

def test_semantic_lineage_survives_revision() -> None:
    a=from_attestation(_att(),namespace="skeleton",kind="execution",stable_id="job-1",revision=1)
    b=from_attestation(_att(),namespace="skeleton",kind="execution",stable_id="job-1",revision=2)
    assert same_semantic_lineage(a,b)
    assert not same_semantic_lineage(b,a)

def test_pq_capabilities_are_declared_without_fake_implementation() -> None:
    ids={item.algorithm for item in CAPABILITIES}
    assert {"ml-dsa-44","ml-dsa-65","ml-dsa-87","slh-dsa"} <= ids
    registry=SignerRegistry()
    with pytest.raises(RuntimeError,match="not installed"):
        registry.sign("ml-dsa-65",b"statement")

def test_signature_negotiation_prefers_first_mutual_algorithm() -> None:
    chosen=negotiate(("ml-dsa-65","ed25519"),("ed25519","ml-dsa-65"))
    assert chosen.algorithm=="ml-dsa-65"
    assert chosen.post_quantum is True

def test_registered_signer_must_return_real_bytes() -> None:
    registry=SignerRegistry(); registry.register("ed25519",lambda payload:b"sig:"+payload)
    assert registry.sign("ed25519",b"x")==b"sig:x"
    registry=SignerRegistry(); registry.register("ed25519",lambda payload:b"")
    with pytest.raises(RuntimeError,match="invalid signature"):
        registry.sign("ed25519",b"x")
