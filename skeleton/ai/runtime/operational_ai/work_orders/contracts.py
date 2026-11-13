"""Canonical, closed and bounded work-order identities; no silent coercion."""
from __future__ import annotations
import hashlib
import math
import re
from skeleton.ai.runtime.operational_ai.authority.canonical import (
    ContractViolation,canonical_bytes,load_json
)
class WorkOrderError(ContractViolation):
    """Untrusted or inconsistent operational claim."""
def refuse(reason):
    raise WorkOrderError(reason)
ID=re.compile(r"[A-Za-z0-9_-]{1,128}\Z",re.ASCII)
SHA=re.compile(r"[0-9a-f]{64}\Z",re.ASCII)
STATES=frozenset(("queued","leased","dispatch-unknown","held","committed","cancelled"))
def identifier(x,label="identity"):
    if type(x) is not str or ID.fullmatch(x) is None:
        refuse("invalid "+label)
    return x
def digest_id(x):
    if type(x) is not str or SHA.fullmatch(x) is None:
        refuse("invalid SHA256 identity")
    return x
def uint(x,*,maximum=2**53-1):
    if type(x) is not int or not 0<=x<=maximum:
        refuse("bounded unsigned integer required")
    return x
def temperature(x):
    if type(x) not in (int,float) or not math.isfinite(x) or not 0.000000001<=x<=2.0:
        refuse("bounded finite sampling temperature required")
    return float(x)
def prompt(x):
    if type(x) is not str:refuse("prompt must be text")
    try:raw=x.encode("utf-8","strict")
    except UnicodeError:refuse("invalid prompt Unicode")
    if not raw or len(raw)>32768 or not x.strip() or b"\0" in raw:
        refuse("unbounded/empty prompt")
    return x
def canonical(x):
    return canonical_bytes(x,ceiling=262144)
def hash_bytes(x):
    if type(x) is not bytes:refuse("digest needs bytes")
    return hashlib.sha256(x).hexdigest()
def fingerprint(x):
    return hash_bytes(canonical(x))
def parse(raw):
    return load_json(raw,ceiling=262144)
