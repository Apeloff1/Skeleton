"""Canonical, bounded JSON with duplicate-key and nonfinite-value refusal."""
import hashlib
import json

class GateViolation(ValueError):
    """An AI request crossed an explicit trust or capability boundary."""

def _pairs(pairs):
    result={}
    for key,val in pairs:
        if key in result: raise GateViolation("duplicate JSON key")
        result[key]=val
    return result

def _constant(val):
    raise GateViolation("nonfinite JSON constant")

def load_json(raw: bytes, *, ceiling: int=524288):
    if type(raw) is not bytes or type(ceiling) is not int or not 1<=ceiling<=1048576:
        raise GateViolation("invalid JSON input")
    if not raw or len(raw)>ceiling: raise GateViolation("JSON byte ceiling")
    try:
        return json.loads(raw.decode("utf-8","strict"), object_pairs_hook=_pairs,
                          parse_constant=_constant)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise GateViolation("malformed JSON") from exc

def canonical(value, *, ceiling: int=524288):
    try:
        raw=json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,
                       separators=(",",":")).encode("utf-8","strict")
        if not raw or len(raw)>ceiling: raise GateViolation("canonical byte ceiling")
        if json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs)!=value:
            raise GateViolation("nonroundtrip canonical value")
        return raw
    except (TypeError,ValueError,UnicodeError,OverflowError,RecursionError) as exc:
        raise GateViolation("noncanonical input") from exc

def fail(reason: str):
    raise GateViolation(reason)

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
