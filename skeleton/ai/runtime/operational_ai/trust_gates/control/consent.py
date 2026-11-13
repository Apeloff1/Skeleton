"""Operator-issued, scope-bound HMAC tokens for a single memory admission.

This is process-local replay protection, not durable cross-process consent
custody. Only the authorized caller may supply the secret and trusted clock.
Neither LLM text nor retrieved evidence can issue its own memory grant.
"""
from __future__ import annotations
import hashlib
import hmac
import re
import secrets
from threading import RLock
from ..contracts import canonical,fail

_NAME=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",re.ASCII)
_SHA=re.compile(r"[0-9a-f]{64}",re.ASCII)
_NONCE=re.compile(r"[0-9a-f]{32}",re.ASCII)

def _principal(value):
    if type(value) is not str or _NAME.fullmatch(value) is None:
        fail("malformed authenticated consent principal")
    return value

class ConsentAuthority:
    def __init__(self,secret,*,maximum_consumed=100000):
        if type(secret) is not bytes or not 32<=len(secret)<=4096:
            fail("operator-held consent HMAC key required")
        if type(maximum_consumed) is not int or not 1<=maximum_consumed<=1000000:
            fail("invalid consent replay-fence ceiling")
        self._key=bytes(secret)
        self._lock=RLock()
        self._seen=set()
        self._maximum=maximum_consumed

    def issue(self,*,tenant,source_id,operator,now,expires,approved):
        if approved is not True:
            fail("memory consent must be explicitly granted")
        for entry in (tenant,source_id,operator):
            _principal(entry)
        if (type(now) is not int or type(expires) is not int
            or not 0<=now<expires<=now+86400):
            fail("invalid consent issue or expiration time")
        record={"schema":"memory-consent.v2","tenant":tenant,
                "source_id":source_id,"operator":operator,
                "issued":now,"expires":expires,"approved":True,
                "nonce":secrets.token_hex(16)}
        mac=hmac.new(self._key,canonical(record),hashlib.sha256).hexdigest()
        return {"record":record,"mac":mac}

    def verify(self,token,*,tenant,source_id,now,consume=True):
        if type(consume) is not bool:
            fail("explicit consumption policy required")
        if type(token) is not dict or set(token)!={"record","mac"}:
            fail("invalid consent token envelope")
        record=token["record"]
        if type(record) is not dict or set(record)!={
            "schema","tenant","source_id","operator","issued",
            "expires","approved","nonce"}:
            fail("invalid consent record fields")
        if record["schema"]!="memory-consent.v2" or record["approved"] is not True:
            fail("wrong memory consent schema or authorization")
        for entry in (record["tenant"],record["source_id"],record["operator"]):
            _principal(entry)
        nonce=record["nonce"]
        if type(nonce) is not str or _NONCE.fullmatch(nonce) is None:
            fail("missing cryptographic consent nonce")
        issued=record["issued"];expires=record["expires"]
        if (type(issued) is not int or type(expires) is not int
            or not 0<=issued<expires<=issued+86400):
            fail("invalid consent record expiration")
        mac=token["mac"]
        if type(mac) is not str or _SHA.fullmatch(mac) is None:
            fail("invalid HMAC digest shape")
        expected=hmac.new(self._key,canonical(record),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac,expected):
            fail("consent authentication mismatch")
        _principal(tenant);_principal(source_id)
        if record["tenant"]!=tenant or record["source_id"]!=source_id:
            fail("memory consent tenant/source confusion")
        if type(now) is not int or not issued<=now<expires:
            fail("memory consent expired or not yet active")
        if consume:
            with self._lock:
                if nonce in self._seen:
                    fail("memory consent token replayed")
                if len(self._seen)>=self._maximum:
                    fail("memory consent replay-fence full")
                self._seen.add(nonce)
        return {"tenant":tenant,"source_id":source_id,"approved":True}
