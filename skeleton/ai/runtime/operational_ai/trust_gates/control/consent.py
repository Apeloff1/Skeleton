"""Explicit, scope- and time-bound HMAC attestations for memory admission.

The caller must keep the HMAC key private and bind it to its own local key
custody; this module never derives a grant from model-generated text.
"""
from __future__ import annotations
import hashlib
import hmac
import json
from ..contracts import canonical,fail

class ConsentAuthority:
    def __init__(self,secret):
        if type(secret) is not bytes or len(secret)<32:
            fail("strong independent consent key required")
        self._key=bytes(secret)

    def issue(self,*,tenant,source_id,operator,now,expires,approved):
        if type(approved) is not bool or not approved:
            fail("consent cannot be inferred")
        if any(type(x) is not str or not x or len(x)>128 for x in (tenant,source_id,operator)):
            fail("invalid consent scope")
        if (type(now) is not int or type(expires) is not int or
            not 0<=now<expires<=now+86400):
            fail("invalid consent expiry")
        record={"schema":"memory-consent.v1","tenant":tenant,"source_id":source_id,
                "operator":operator,"issued":now,"expires":expires,"approved":True}
        mac=hmac.new(self._key,canonical(record),hashlib.sha256).hexdigest()
        return {"record":record,"mac":mac}

    def verify(self,token,*,tenant,source_id,now):
        if type(token) is not dict or set(token)!={"record","mac"}:
            fail("malformed consent token")
        record=token["record"]
        if type(record) is not dict or set(record)!={
            "schema","tenant","source_id","operator","issued","expires","approved"}:
            fail("consent content shape mismatch")
        if record["schema"]!="memory-consent.v1" or record["approved"] is not True:
            fail("consent version or authority invalid")
        if type(now) is not int or not record["issued"]<=now<record["expires"]:
            fail("consent not currently valid")
        if record["tenant"]!=tenant or record["source_id"]!=source_id:
            fail("cross-scope consent token")
        supplied=token["mac"]
        if type(supplied) is not str or len(supplied)!=64:
            fail("consent authenticator shape invalid")
        expected=hmac.new(self._key,canonical(record),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied,expected):
            fail("consent token authentication failed")
        return {"tenant":tenant,"source_id":source_id,"approved":True}
