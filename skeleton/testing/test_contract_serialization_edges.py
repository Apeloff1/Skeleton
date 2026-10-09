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


def test_canonical_json_rejects_nonportable_integer_range():
 import pytest
 from skeleton.contracts.canonical import CanonicalContractError,canonical_json_bytes
 assert canonical_json_bytes({"n":9007199254740991})
 for value in (9007199254740992,-9007199254740992):
  with pytest.raises(CanonicalContractError,match="portable JSON range"):
   canonical_json_bytes({"n":value})

def test_canonical_json_rejects_negative_zero_but_accepts_positive_zero():
 import pytest
 from skeleton.contracts.canonical import CanonicalContractError,canonical_json_bytes
 assert canonical_json_bytes({"n":0.0})==b'{"n":0.0}'
 with pytest.raises(CanonicalContractError,match="negative zero"):
  canonical_json_bytes({"n":-0.0})


def test_canonical_envelope_rejects_schema_booleans_and_numeric_aliases():
 for ambiguous in (True,1.0):
  with pytest.raises(CanonicalContractError,match="unsupported schema version"):
   CanonicalEnvelope(ambiguous,"vol003.contract",Identity("repo","a"*40),(),(),{}).canonical_payload()


def test_canonical_envelope_requires_typed_identity_and_structural_fields():
 cases=(
  {"kind":123},
  {"identity":{"repository":"repo","commit_sha":"a"*40}},
  {"evidence":({"source":"repo","digest":"b"*64},)},
  {"constraints":("ok",42)},
  {"payload":["not-an-object"]},
 )
 for override in cases:
  fields={
   "schema_version":1,
   "kind":"vol003.contract",
   "identity":Identity("repo","a"*40),
   "evidence":(EvidenceRef("repo","b"*64),),
   "constraints":("safe",),
   "payload":{},
  }
  fields.update(override)
  with pytest.raises(CanonicalContractError):
   CanonicalEnvelope(**fields).canonical_payload()



def test_canonical_envelope_rejects_malformed_metadata_fields():
    base = {
        "schema_version": 1,
        "kind": "vol003.contract",
        "identity": Identity("repo", "a" * 40),
        "evidence": (EvidenceRef("repo", "b" * 64),),
        "constraints": ("safe",),
        "payload": {},
    }
    invalid_cases = (
        {"identity": Identity(123, "a" * 40)},
        {"identity": Identity("repo", chr(0xD800))},
        {"evidence": (EvidenceRef("", "b" * 64),)},
        {"evidence": (EvidenceRef("repo", chr(0xDFFF)),)},
        {"constraints": (chr(0xD800),)},
    )
    for override in invalid_cases:
        fields = {**base, **override}
        with pytest.raises(CanonicalContractError):
            CanonicalEnvelope(**fields).canonical_payload()
