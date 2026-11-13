"""Canonical, bounded, closed-schema trust and identity functions.

Every persisted or issued identity is computed from exactly these UTF8 bytes.
No fuzzy coercion, NaN, noncanonical dictionaries, duplicate JSON keys,
UTF8 surrogates, unconstrained integer fields or implicit operator consent.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import math
import re
from dataclasses import dataclass
from typing import Any

MAX_REQUEST_BYTES=262144
IDENTIFIER=re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z",re.ASCII)
SHA256=re.compile(r"[a-f0-9]{64}\Z",re.ASCII)
class CognitionError(ValueError):
    """A hard operational or source-integrity boundary rejected input."""
def refuse(message):
    raise CognitionError(message)
def identifier(value,*,label="identifier"):
    if type(value) is not str or IDENTIFIER.fullmatch(value) is None:
        refuse("invalid "+label)
    return value
def sha(value,*,label="digest"):
    if type(value) is not str or SHA256.fullmatch(value) is None:
        refuse("invalid "+label)
    return value
def integer(value,*,minimum=0,maximum=2**53-1):
    if type(value) is not int or not minimum<=value<=maximum:
        refuse("invalid exact bounded integer")
    return value
def number(value,*,minimum=0,maximum=1e12):
    if type(value) not in (int,float) or not math.isfinite(value) or not minimum<=value<=maximum:
        refuse("invalid finite number")
    return float(value)
def text(value,*,maximum=32768,allow_empty=False):
    if type(value) is not str:refuse("text input required")
    try:raw=value.encode("utf-8","strict")
    except UnicodeError:refuse("invalid Unicode")
    if len(raw)>maximum or b"\x00" in raw or (not allow_empty and not value.strip()):
        refuse("invalid text byte bounds")
    return value
def strict_pairs(entries):
    value={}
    for k,v in entries:
        if k in value:refuse("duplicate JSON key")
        value[k]=v
    return value
def finite_constant(_):
    refuse("nonfinite JSON constant")
def loads(raw,*,maximum=MAX_REQUEST_BYTES):
    if type(raw) is not bytes or not 1<=len(raw)<=maximum:
        refuse("bounded UTF8 JSON required")
    try:
        return json.loads(raw.decode("utf-8","strict"),object_pairs_hook=strict_pairs,
                          parse_constant=finite_constant)
    except (ValueError,UnicodeError,RecursionError,TypeError) as exc:
        raise CognitionError("untrusted JSON decoding refused") from exc
def canonical(value,*,maximum=MAX_REQUEST_BYTES):
    try:
        result=json.dumps(value,sort_keys=True,separators=(",",":"),
                          allow_nan=False,ensure_ascii=False).encode("utf-8","strict")
        if not 1<=len(result)<=maximum:refuse("canonical byte ceiling")
        if loads(result,maximum=maximum)!=value:refuse("non-roundtrip canonical object")
        return result
    except (UnicodeError,TypeError,ValueError,RecursionError,OverflowError) as exc:
        raise CognitionError("noncanonical object") from exc
def hash_bytes(raw):
    if type(raw) is not bytes:refuse("digest requires bytes")
    return hashlib.sha256(raw).hexdigest()
def fingerprint(obj):
    return hash_bytes(canonical(obj))
def same_digest(left,right):
    return hmac.compare_digest(sha(left),sha(right))
def exact(obj,fields):
    if type(obj) is not dict or set(obj)!=set(fields) or any(type(k) is not str for k in obj):
        refuse("closed object fields required")
    return obj
@dataclass(frozen=True,slots=True)
class Scope:
    tenant:str
    subject:str
    model_sha256:str
    tokenizer_sha256:str
    def __post_init__(self):
        identifier(self.tenant,label="tenant")
        identifier(self.subject,label="subject")
        sha(self.model_sha256,label="model")
        sha(self.tokenizer_sha256,label="tokenizer")
    def receipt(self):
        return {"tenant":self.tenant,"subject":self.subject,
                "model_sha256":self.model_sha256,
                "tokenizer_sha256":self.tokenizer_sha256}
    def digest(self):
        return fingerprint(self.receipt())
    def assert_same(self,other):
        if type(other) is not Scope or self!=other:
            refuse("cross-principal/model epoch")
        return self
