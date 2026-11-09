from __future__ import annotations
import pytest
from skeleton.ai.runtime.provenance.commitments import Commitment,canonical_bytes
from skeleton.ai.runtime.provenance.attestation import Attestation,Subject,Witness
from skeleton.ai.runtime.provenance.crypto_inventory import CryptoPrimitive,inventory_manifest,select_for_issuance

def test_commitment_is_algorithm_and_profile_explicit() -> None:
    a=Commitment.of({"b":2,"a":1},"sha256")
    b=Commitment.of({"a":1,"b":2},"sha256")
    assert a==b
    assert a.to_dict()["profile"]=="skeleton.canonical-json.v1"

def test_canonical_profile_rejects_float_ambiguity() -> None:
    with pytest.raises(ValueError,match="floating"):
        canonical_bytes({"score":0.1})

def test_attestation_separates_subject_and_predicate() -> None:
    subject=Subject("execution",Commitment.of({"request":"a","output":"b"}))
    att=Attestation((subject,),{"runtime":"native","policy":"p1"})
    assert att.verify_offline()
    assert att.statement_dict()["subjects"][0]["name"]=="execution"

def test_witness_is_optional_and_bound_to_statement() -> None:
    subject=Subject("execution",Commitment.of({"id":"x"}))
    att=Attestation((subject,),{"result":"ok"}).with_witness("transparency","witness-a")
    assert att.verify_offline()
    bad=Witness("transparency","witness-b",Commitment.of({"different":True}))
    assert not Attestation(att.subjects,att.predicate,(bad,)).verify_offline()

def test_duplicate_subject_or_witness_authority_fails_closed() -> None:
    s=Subject("execution",Commitment.of({"id":"x"}))
    with pytest.raises(ValueError,match="subject names"):
        Attestation((s,s),{})
    att=Attestation((s,),{}).with_witness("log","a")
    with pytest.raises(ValueError,match="unique"):
        att.with_witness("log","a")

def test_crypto_inventory_is_unique_and_machine_readable() -> None:
    manifest=inventory_manifest()
    ids=[p["primitive_id"] for p in manifest["primitives"]]
    assert len(ids)==len(set(ids))
    assert select_for_issuance(2026).algorithm=="sha256"

def test_crypto_retirement_separates_issuance_from_verification() -> None:
    p=CryptoPrimitive("legacy","sha256","legacy",2020,2030,2090)
    assert p.can_issue(2030) and not p.can_issue(2031)
    assert p.can_verify(2031) and p.can_verify(2090) and not p.can_verify(2091)
