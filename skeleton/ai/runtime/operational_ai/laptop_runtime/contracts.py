"""Exact laptop API contracts without implicit authority from client or model text."""
from __future__ import annotations
import hashlib
import hmac
import math
import re
from skeleton.ai.runtime.operational_ai.authority.canonical import (
    ContractViolation,load_json,canonical_bytes,require_digest
)
_ID=re.compile(r"[A-Za-z0-9_-]{1,128}\Z",re.ASCII)

def refuse(message):
    raise ContractViolation(message)

def identifier(value,label="identifier"):
    if type(value) is not str or _ID.fullmatch(value) is None: refuse("invalid "+label)
    return value

def exact(data,required=(),optional=()):
    if type(data) is not dict or any(type(k) is not str for k in data):
        refuse("request must be an object")
    needed=set(required);allowed=needed|set(optional)
    if not needed.issubset(data.keys()) or set(data)-allowed:
        refuse("unknown or absent request fields")
    return data

def utf8(value,*,maximum=32768,allow_empty=False):
    if type(value) is not str: refuse("UTF-8 text required")
    try:size=len(value.encode("utf-8","strict"))
    except UnicodeError: refuse("invalid Unicode")
    if not 0<=size<=maximum or (not allow_empty and not value.strip()):
        refuse("bounded nonempty UTF-8 required")
    if chr(0) in value:refuse("NUL input forbidden")
    return value

def number(value,*,minimum,maximum):
    if type(value) not in (int,float) or not math.isfinite(value):
        refuse("finite numerical input required")
    if not minimum<=value<=maximum:refuse("numeric bound exceeded")
    return float(value)

def nonnegative(value,*,maximum):
    if type(value) is not int or not 0<=value<=maximum:
        refuse("bounded unsigned integer required")
    return value

def safe_json(raw,*,ceiling=65536):
    return load_json(raw,ceiling=ceiling)

def canonical(value,*,ceiling=262144):
    return canonical_bytes(value,ceiling=ceiling)

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def identity_hash(value):
    return require_digest(value)

def token(value):
    if type(value) is not str or not 32<=len(value)<=512:
        refuse("invalid bearer token shape")
    if any(ord(c)<33 or ord(c)>126 for c in value):
        refuse("bearer token must be printable ASCII without whitespace")
    return value

def same_token(left,right):
    return hmac.compare_digest(token(left).encode("ascii"),token(right).encode("ascii"))
