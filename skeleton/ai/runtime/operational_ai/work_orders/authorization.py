"""HMAC-authenticated, time- and job-scoped operator admission receipts.

The signing secret must come from trusted operator runtime configuration and
never from a prompt/model/retrieval source. Expiration is judged against an
operator-supplied trusted clock, not a model-produced timestamp. Atomic nonce
consumption occurs in SignedIngress, not in this pure verifier.
"""
from __future__ import annotations
import hmac
import hashlib
import secrets
import re
from .model import WorkOrder
from .contracts import canonical,identifier,digest_id,hash_bytes,uint,refuse

_NONCE=re.compile(r"[0-9a-f]{32}\Z",re.ASCII)
_MAC=re.compile(r"[0-9a-f]{64}\Z",re.ASCII)
_REQUIRED=frozenset(("schema","tenant","subject","model_sha256",
    "job_id","request_sha256","issued_at","expires_at","nonce","right"))

class OperatorAuthority:
    def __init__(self,key):
        if type(key) is not bytes or not 32<=len(key)<=4096:
            refuse("operator-provisioned HMAC key must have >=256 bits")
        self._key=bytes(key)

    def issue(self,order,*,issued_at,expires_at,approved):
        if not isinstance(order,WorkOrder):
            refuse("cannot sign unbound work")
        if approved is not True:
            refuse("operator approval absent; model may not self-authorize")
        uint(issued_at);uint(expires_at)
        if not issued_at<expires_at<=issued_at+3600:
            refuse("invalid bounded admission validity")
        record={"schema":"ai-operator-admission.v1",
            "tenant":order.tenant,"subject":order.subject,
            "model_sha256":order.model_sha256,
            "job_id":order.job_id,"request_sha256":order.request_sha256(),
            "issued_at":issued_at,"expires_at":expires_at,
            "nonce":secrets.token_hex(16),"right":"submit"}
        mac=hmac.new(self._key,canonical(record),hashlib.sha256).hexdigest()
        return {"record":record,"mac":mac}

    def verify(self,ticket,order,*,observed_at):
        if not isinstance(order,WorkOrder):
            refuse("typed work-order required for token verification")
        if type(ticket) is not dict or set(ticket)!={"record","mac"}:
            refuse("unknown operator ticket envelope")
        record=ticket["record"];mac=ticket["mac"]
        if type(record) is not dict or set(record)!=_REQUIRED:
            refuse("invalid operator approval fields")
        if type(mac) is not str or _MAC.fullmatch(mac) is None:
            refuse("malformed operator HMAC digest")
        for name in ("tenant","subject","job_id"):
            identifier(record[name],name)
        for name in ("model_sha256","request_sha256"):
            digest_id(record[name])
        nonce=record["nonce"]
        if type(nonce) is not str or _NONCE.fullmatch(nonce) is None:
            refuse("missing admission nonce")
        if record["schema"]!="ai-operator-admission.v1" or record["right"]!="submit":
            refuse("wrong privilege or schema")
        issued=uint(record["issued_at"]);expires=uint(record["expires_at"])
        if not issued<expires<=issued+3600:
            refuse("unbounded grant lifetime")
        uint(observed_at)
        if not issued<=observed_at<expires:
            refuse("grant expired or not yet active")
        if (record["tenant"],record["subject"],record["model_sha256"],
            record["job_id"],record["request_sha256"])!=(
            order.tenant,order.subject,order.model_sha256,
            order.job_id,order.request_sha256()):
            refuse("signed grant is not bound to request, model and operator")
        signed=hmac.new(self._key,canonical(record),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac,signed):
            refuse("operator HMAC authentication failed")
        return {"nonce_sha256":hash_bytes(bytes.fromhex(nonce)),
            "tenant":order.tenant,"subject":order.subject,
            "request_sha256":order.request_sha256(),
            "expires_at":expires}
