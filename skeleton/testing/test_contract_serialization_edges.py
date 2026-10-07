from __future__ import annotations
import pytest
from skeleton.contracts.canonical import CanonicalContractError,CanonicalEnvelope,EvidenceRef,Identity,canonical_conformance_vector

def env(payload,*,constraints=("z","a","z")):
 return CanonicalEnvelope(1,"vol003.contract",Identity("Apeloff1/Skeleton","a"*40),(EvidenceRef("repo","b"*64),),constraints,payload)

def test_conformance_vector_is_deterministic_and_authority_neutral():
 left=canonical_conformance_vector(env({"雪":"Ω","nested":{"b":2,"a":1}}))
 right=canonical_conformance_vector(env({"nested":{"a":1,"b":2},"雪":"Ω"},constraints=("a","z")))
 assert left==right
 assert left["digest"]==env({"nested":{"a":1,"b":2},"雪":"Ω"},constraints=("a","z")).digest
 assert bytes.fromhex(left["canonical_hex"])==env({"雪":"Ω","nested":{"b":2,"a":1}}).canonical_bytes
 assert left["authority_scope"]=="contract-conformance-only"
 assert left["constraints"]==("a","z")
 assert len(left["evidence_identities"])==1

def test_conformance_vector_rejects_untyped_input():
 with pytest.raises(CanonicalContractError,match="CanonicalEnvelope"):canonical_conformance_vector({"payload":{}})
