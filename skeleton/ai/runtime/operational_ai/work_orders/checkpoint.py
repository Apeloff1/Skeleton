"""Operator-key-authenticated source-state audit checkpoint.

An HMAC protects a snapshot against modification by actors without the
operator key. It is not an off-machine or regulatory source attestation.
"""
from __future__ import annotations
import hmac
import hashlib
from .contracts import canonical,identifier,digest_id,uint,refuse
from .store import WorkOrderStore

class CheckpointAuthority:
    def __init__(self,operator_key):
        if type(operator_key) is not bytes or not 32<=len(operator_key)<=4096:
            refuse("operator HMAC key required")
        self._key=bytes(operator_key)

    def seal(self,queue,*,tenant,observed_at):
        if not isinstance(queue,WorkOrderStore):
            refuse("real state queue required")
        tenant=identifier(tenant)
        observed_at=uint(observed_at)
        audit=queue.audit()
        body={"schema":"ai-work-operator-checkpoint.v1","tenant":tenant,
              "audit_head_sha256":digest_id(audit["head_sha256"]),
              "events":audit["events"],"jobs":audit["jobs"],
              "observed_at":observed_at,"release_certified":False}
        mac=hmac.new(self._key,canonical(body),hashlib.sha256).hexdigest()
        return {"body":body,"mac":mac}

    def verify(self,checkpoint,queue,*,tenant):
        if type(checkpoint) is not dict or set(checkpoint)!={"body","mac"}:
            refuse("unknown operator checkpoint envelope")
        body=checkpoint["body"];mac=checkpoint["mac"]
        if type(body) is not dict or set(body)!={"schema","tenant",
              "audit_head_sha256","events","jobs","observed_at","release_certified"}:
            refuse("checkpoint unexpected fields")
        if (body["schema"]!="ai-work-operator-checkpoint.v1" or
            body["release_certified"] is not False or
            body["tenant"]!=identifier(tenant)):
            refuse("mismatched checkpoint scope/authority")
        digest_id(body["audit_head_sha256"])
        uint(body["events"]);uint(body["jobs"]);uint(body["observed_at"])
        if type(mac) is not str or len(mac)!=64:
            refuse("invalid checkpoint signature")
        correct=hmac.new(self._key,canonical(body),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(correct,mac):
            refuse("operator integrity checkpoint authentication failure")
        audit=queue.audit()
        if (audit["head_sha256"]!=body["audit_head_sha256"] or
            audit["events"]!=body["events"] or audit["jobs"]!=body["jobs"]):
            refuse("authenticated checkpoint does not match current queue")
        return {"status":"operator-key-checkpoint-verified",
            "source_state_consistent":True,
            "external_attestation":False,"release_certified":False}
