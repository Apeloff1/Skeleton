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
    policy=import_module("."+name,__package__+".policies")
    policy.check(record)
    return {"schema":"ai-reliability-receipt.v1","domain":name,
            "status":"input-claim-validated-not-proven",
            "record_sha256":sha256(raw),"bytes":len(raw),
            "real_native_inference_tested":False,"release_certified":False}
