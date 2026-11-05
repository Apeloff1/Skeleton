"""Require actual spine identity plus independently supplied bounded evidence."""
from __future__ import annotations
from dataclasses import dataclass
from ..contracts import fail
from .evidence_bundle import EvidenceBundle,BundleReceipt

REQUIRED_INFERENCE=("native_identity","tokenizer_custody","model_capacity",
    "memory_pressure","admission_queue","context_packing",
    "prompt_roles","session_scope","lease_epoch")

@dataclass(frozen=True,slots=True)
class Preflight:
    receipt:BundleReceipt
    tenant:str
    subject:str
    model_sha256:str
    tokenizer_sha256:str
    operation:str="native-generation"
    native_generation_performed:bool=False

def inspect(worker,records):
    if type(records) is not dict or set(records)!=set(REQUIRED_INFERENCE):
        fail("native inference requires complete explicit evidence set")
    try:
        actual=worker.spine.identity
        backend=worker.spine.backend
        if (actual.model_sha256!=backend.model_digest or
            actual.tokenizer_sha256!=backend.tokenizer_digest):
            fail("actual backend differs from authoritative model and tokenizer")
    except AttributeError as exc:
        raise ValueError("real production spine unavailable") from exc
    bundle=EvidenceBundle()
    for domain in REQUIRED_INFERENCE:
        record=records[domain]
        identity=record.get("identity") if type(record) is dict else None
        if type(identity) is not dict or (
            identity.get("tenant")!=actual.tenant or
            identity.get("subject")!=actual.subject or
            identity.get("model_sha256")!=actual.model_sha256):
            fail("untrusted caller/model admission evidence")
        bundle.add(domain,record)
    proof=bundle.seal(required=REQUIRED_INFERENCE)
    return Preflight(proof,actual.tenant,actual.subject,
                     actual.model_sha256,actual.tokenizer_sha256)
