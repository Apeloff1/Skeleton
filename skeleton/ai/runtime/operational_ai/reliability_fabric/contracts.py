"""Finite canonical JSON, duplicate-key refusal and stable digest receipts."""
from __future__ import annotations
import hashlib
import json
import math
class Rejected(ValueError):
    """Closed AI runtime trust boundary rejected an unproven claim."""

def fail(reason):
    raise Rejected(reason)

def _pairs(items):
    result={}
    for key,value in items:
        if key in result:fail("duplicate JSON property")
        result[key]=value
    return result

def _constant(text):
    fail("nonfinite JSON constant")

def strict_json(raw,*,maximum=524288):
    if type(raw) is not bytes or type(maximum) is not int or not 1<=maximum<=1048576:
        fail("invalid serialized input ceiling")
    if not 1<=len(raw)<=maximum:fail("JSON byte ceiling")
    try:
        value=json.loads(raw.decode("utf-8","strict"),object_pairs_hook=_pairs,
                         parse_constant=_constant)
        # Reject escaped lone surrogates before treating operator evidence as valid.
        canonical(value,maximum=maximum)
        return value
    except (UnicodeError,TypeError,ValueError,RecursionError) as exc:
        raise Rejected("invalid UTF8 or ambiguous JSON") from exc

def canonical(obj,*,maximum=524288):
    if type(maximum) is not int or not 1<=maximum<=1048576:
        fail("invalid canonical budget")
    try:
        raw=json.dumps(obj,sort_keys=True,ensure_ascii=False,allow_nan=False,
                       separators=(",",":")).encode("utf-8","strict")
        if not 1<=len(raw)<=maximum:fail("canonical bytes over ceiling")
        check=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs)
        if check!=obj:fail("noncanonical JSON roundtrip")
        return raw
    except (UnicodeError,TypeError,ValueError,OverflowError,RecursionError) as exc:
        raise Rejected("object cannot be canonically encoded") from exc

def sha256(raw):
    if type(raw) is not bytes:fail("SHA256 requires exact bytes")
    return hashlib.sha256(raw).hexdigest()
