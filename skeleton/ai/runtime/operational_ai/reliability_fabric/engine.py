"""Validated input claim receipts with actual per-domain semantic checking."""
from __future__ import annotations
from functools import lru_cache
from importlib import resources,import_module
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

_POLICIES = {
    "native_identity": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.native_identity"),
    "weight_custody": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.weight_custody"),
    "tokenizer_custody": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.tokenizer_custody"),
    "model_capacity": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.model_capacity"),
    "memory_pressure": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.memory_pressure"),
    "admission_queue": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.admission_queue"),
    "request_dedupe": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.request_dedupe"),
    "context_packing": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.context_packing"),
    "prompt_roles": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.prompt_roles"),
    "output_receipt": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.output_receipt"),
    "stream_sequence": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.stream_sequence"),
    "stream_backpressure": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.stream_backpressure"),
    "cancellation": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.cancellation"),
    "retry_budget": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.retry_budget"),
    "session_scope": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.session_scope"),
    "memory_consent": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.memory_consent"),
    "memory_deletion": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.memory_deletion"),
    "retrieval_integrity": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.retrieval_integrity"),
    "citation_provenance": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.citation_provenance"),
    "tool_grant": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.tool_grant"),
    "tool_intent": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.tool_intent"),
    "audit_journal": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.audit_journal"),
    "outbox_ack": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.outbox_ack"),
    "snapshot_cas": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.snapshot_cas"),
    "backup_integrity": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.backup_integrity"),
    "restore_order": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.restore_order"),
    "key_rotation": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.key_rotation"),
    "lease_epoch": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.lease_epoch"),
    "transport_local": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.transport_local"),
    "http_framing": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.http_framing"),
    "device_probe": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.device_probe"),
    "installer_attestation": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.installer_attestation"),
    "process_isolation": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.process_isolation"),
    "health_circuit": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.health_circuit"),
    "metrics_sampling": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.metrics_sampling"),
    "evaluation_evidence": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.evaluation_evidence"),
    "canary_evidence": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.canary_evidence"),
    "rollout_authority": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.rollout_authority"),
    "release_qualification": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.release_qualification"),
    "privacy_boundary": lambda: import_module("skeleton.ai.runtime.operational_ai.reliability_fabric.policies.privacy_boundary"),
}

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
    policy=_POLICIES[name]()
    policy.check(record)
    return {"schema":"ai-reliability-receipt.v1","domain":name,
            "status":"input-claim-validated-not-proven",
            "record_sha256":sha256(raw),"bytes":len(raw),
            "real_native_inference_tested":False,"release_certified":False}
