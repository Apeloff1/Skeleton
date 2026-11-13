"""Tamper-evident journal replay cursor scoped to one session and model."""
from __future__ import annotations
import base64
import hashlib
import hmac
from ..authority.canonical import ContractViolation,canonical_bytes,load_json,require_digest
from ..authority.identity import require_id


def issue(secret:bytes,*,stream:str,model_digest:str,revision:int)->str:
    if not isinstance(secret,bytes) or len(secret)<32:
        raise ContractViolation("cursor signing key too short")
    require_id(stream,field="stream")
    require_digest(model_digest,field="model digest")
    if type(revision) is not int or not 0<=revision<=2**31-1:
        raise ContractViolation("invalid cursor revision")
    data=canonical_bytes({"version":1,"stream":stream,"model":model_digest,"revision":revision})
    tag=hmac.new(secret,data,hashlib.sha256).digest()
    return base64.urlsafe_b64encode(data+tag).rstrip(b"=").decode("ascii")


def parse(secret:bytes,cursor:str,*,stream:str,model_digest:str)->int:
    if not isinstance(secret,bytes) or len(secret)<32:
        raise ContractViolation("cursor signing key too short")
    if type(cursor) is not str or not 30<=len(cursor)<=512 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in cursor):
        raise ContractViolation("malformed cursor")
    try:
        raw=base64.urlsafe_b64decode(cursor+"="*((-len(cursor))%4))
    except (ValueError,TypeError) as exc:
        raise ContractViolation("invalid cursor encoding") from exc
    if len(raw)<=32 or len(raw)>512:
        raise ContractViolation("invalid cursor byte budget")
    data,tag=raw[:-32],raw[-32:]
    if not hmac.compare_digest(hmac.new(secret,data,hashlib.sha256).digest(),tag):
        raise ContractViolation("cursor authentication mismatch")
    payload=load_json(data,ceiling=480)
    if not isinstance(payload,dict) or set(payload)!={"version","stream","model","revision"}:
        raise ContractViolation("invalid cursor fields")
    if payload["version"]!=1 or payload["stream"]!=stream or payload["model"]!=model_digest:
        raise ContractViolation("cursor scope mismatch")
    revision=payload["revision"]
    if type(revision) is not int or not 0<=revision<=2**31-1:
        raise ContractViolation("invalid cursor revision")
    return revision
