"""Validated input claim receipts with actual per-domain semantic checking."""
from __future__ import annotations
from functools import lru_cache
from importlib import resources
from .contracts import Rejected,fail,canonical,sha256,strict_json
from .catalog import domains

@lru_cache(maxsize=48)
def _schema(name):
    if name not in domains():fail("unregistered AI fabric domain")
    raw=resources.files(__package__).joinpath("schemas",name+".json").read_bytes()
    spec=strict_json(raw,maximum=131072)
    if type(spec) is not dict or set(spec)!={"type","fields"} or spec["type"]!="object":
        fail("invalid audited source schema")
    return spec

def validate(name,record):
    if name not in domains():fail("unknown AI fabric boundary")
    raw=canonical(record)
    from .schema import check
    check(record,_schema(name))
    identity=record["identity"]
    if identity["tenant"] in ("*","root","all") or identity["subject"] in ("*","root","all"):
        fail("wildcard principal forbidden")
    if identity["scope"]!=identity["tenant"]+":"+identity["subject"]:
        fail("caller scope does not bind tenant/subject")
    if identity["model_sha256"]=="0"*64:
        fail("missing model fingerprint")
    timing=record["timing"]
    if not timing["issued_ns"]<=timing["observed_ns"]<timing["expires_ns"]:
        fail("expired or not-yet-valid input evidence")
    if timing["expires_ns"]-timing["issued_ns"]>1_000_000_000:
        fail("unbounded evidence lifetime")
    approval=record["approval"]
    if not approval["operator_approved"] or not approval["source_verified"]:
        fail("unapproved external evidence")
    if approval["source_sha256"]=="0"*64:
        fail("zero source digest")
    if name == "native_identity":
        from .policies import native_identity as policy
    elif name == "weight_custody":
        from .policies import weight_custody as policy
    elif name == "tokenizer_custody":
        from .policies import tokenizer_custody as policy
    elif name == "model_capacity":
        from .policies import model_capacity as policy
    elif name == "memory_pressure":
        from .policies import memory_pressure as policy
    elif name == "admission_queue":
        from .policies import admission_queue as policy
    elif name == "request_dedupe":
        from .policies import request_dedupe as policy
    elif name == "context_packing":
        from .policies import context_packing as policy
    elif name == "prompt_roles":
        from .policies import prompt_roles as policy
    elif name == "output_receipt":
        from .policies import output_receipt as policy
    elif name == "stream_sequence":
        from .policies import stream_sequence as policy
    elif name == "stream_backpressure":
        from .policies import stream_backpressure as policy
    elif name == "cancellation":
        from .policies import cancellation as policy
    elif name == "retry_budget":
        from .policies import retry_budget as policy
    elif name == "session_scope":
        from .policies import session_scope as policy
    elif name == "memory_consent":
        from .policies import memory_consent as policy
    elif name == "memory_deletion":
        from .policies import memory_deletion as policy
    elif name == "retrieval_integrity":
        from .policies import retrieval_integrity as policy
    elif name == "citation_provenance":
        from .policies import citation_provenance as policy
    elif name == "tool_grant":
        from .policies import tool_grant as policy
    elif name == "tool_intent":
        from .policies import tool_intent as policy
    elif name == "audit_journal":
        from .policies import audit_journal as policy
    elif name == "outbox_ack":
        from .policies import outbox_ack as policy
    elif name == "snapshot_cas":
        from .policies import snapshot_cas as policy
    elif name == "backup_integrity":
        from .policies import backup_integrity as policy
    elif name == "restore_order":
        from .policies import restore_order as policy
    elif name == "key_rotation":
        from .policies import key_rotation as policy
    elif name == "lease_epoch":
        from .policies import lease_epoch as policy
    elif name == "transport_local":
        from .policies import transport_local as policy
    elif name == "http_framing":
        from .policies import http_framing as policy
    elif name == "device_probe":
        from .policies import device_probe as policy
    elif name == "installer_attestation":
        from .policies import installer_attestation as policy
    elif name == "process_isolation":
        from .policies import process_isolation as policy
    elif name == "health_circuit":
        from .policies import health_circuit as policy
    elif name == "metrics_sampling":
        from .policies import metrics_sampling as policy
    elif name == "evaluation_evidence":
        from .policies import evaluation_evidence as policy
    elif name == "canary_evidence":
        from .policies import canary_evidence as policy
    elif name == "rollout_authority":
        from .policies import rollout_authority as policy
    elif name == "release_qualification":
        from .policies import release_qualification as policy
    elif name == "privacy_boundary":
        from .policies import privacy_boundary as policy
    else:
        fail('unregistered AI fabric domain')
    policy.check(record)
    return {"schema":"ai-reliability-receipt.v1","domain":name,
            "status":"input-claim-validated-not-proven",
            "record_sha256":sha256(raw),"bytes":len(raw),
            "real_native_inference_tested":False,"release_certified":False}
