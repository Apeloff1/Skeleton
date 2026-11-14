"""Opaque authenticated keyset cursors for owner-scoped bounded job listings."""
from __future__ import annotations
import base64
import hashlib
import hmac
from .canonical import encode, decode, require_int
from .errors import deny
from .spec import require_id


class CursorCodec:
    def __init__(self,key:bytes):
        if type(key) is not bytes or len(key)<32 or len(key)>4096:
            deny("cursor-key")
        self._key=key

    def seal(self,*,tenant:str,last_job_id:str,issued_ms:int,expires_ms:int)->str:
        require_id(tenant,"tenant")
        require_id(last_job_id,"cursor-id")
        require_int(issued_ms,0,2**63-1,"cursor-issued")
        require_int(expires_ms,0,2**63-1,"cursor-expiry")
        if not 0<expires_ms-issued_ms<=300000:
            deny("cursor-ttl")
        raw=encode({"schema":"skeleton.ai.jobs.cursor.v1","tenant":tenant,
                    "last_job_id":last_job_id,"issued_ms":issued_ms,
                    "expires_ms":expires_ms})
        mac=hmac.new(self._key,raw,hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw+mac).decode("ascii").rstrip("=")

    def open(self,cursor:str,*,tenant:str,now_ms:int)->str:
        require_id(tenant,"tenant")
        require_int(now_ms,0,2**63-1,"cursor-clock")
        if type(cursor) is not str or not 16<=len(cursor)<=2048:
            deny("cursor-format")
        try:
            payload=base64.urlsafe_b64decode(cursor+"="*((-len(cursor))%4))
        except (ValueError,TypeError):
            deny("cursor-base64")
        if len(payload)<33:
            deny("cursor-length")
        raw,mac=payload[:-32],payload[-32:]
        expected=hmac.new(self._key,raw,hashlib.sha256).digest()
        if not hmac.compare_digest(expected,mac):
            deny("cursor-mac")
        item=decode(raw)
        if item.get("schema")!="skeleton.ai.jobs.cursor.v1" or item.get("tenant")!=tenant:
            deny("cursor-scope")
        if not item["issued_ms"]<=now_ms<item["expires_ms"]:
            deny("cursor-expired")
        return require_id(item["last_job_id"],"cursor-id")
