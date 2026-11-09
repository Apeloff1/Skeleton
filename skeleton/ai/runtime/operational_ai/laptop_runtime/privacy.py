"""Permitlist-only operator telemetry with no prompts, tokens or source passages."""
from __future__ import annotations
from .contracts import refuse

_FIELDS=frozenset({"status","error_class","release_certified","model_sha256",
                   "tokenizer_sha256","operation","outcome","elapsed_ns"})

def safe_record(raw):
    if type(raw) is not dict:refuse("telemetry record required")
    result={}
    for key in _FIELDS:
        if key not in raw:continue
        value=raw[key]
        if key=="elapsed_ns":
            if type(value) is not int or not 0<=value<=3600000000000:
                refuse("invalid elapsed time")
        elif key in ("release_certified",):
            if type(value) is not bool:refuse("invalid release flag")
        else:
            if type(value) is not str or not value or len(value)>128:
                refuse("unbounded operator telemetry")
        result[key]=value
    return result
