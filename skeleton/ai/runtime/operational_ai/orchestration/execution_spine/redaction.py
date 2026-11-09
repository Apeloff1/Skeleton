"""Bounded diagnostic redaction: no prompts, keys, source passages or responses."""
from __future__ import annotations
from hashlib import sha256
from .contracts import canonical,SpineError
_SAFE_KEYS={'state','revision','request_id','session','status','error_class','duration_ns',
            'prompt_tokens','generated_tokens','model_sha256','tokenizer_sha256','event_key',
            'pending_count','queue_depth','result','attempts','op','head','sha256'}
def safe_diagnostic(payload:dict)->dict:
    if not isinstance(payload,dict) or len(payload)>64:raise SpineError('invalid diagnostic payload')
    result={}
    for key,value in payload.items():
        if key not in _SAFE_KEYS:
            result[key]='[redacted]'
            continue
        if isinstance(value,(str,int,float,bool)) or value is None:
            if isinstance(value,str) and len(value)>128:
                result[key]='[redacted oversized value]'
            else:result[key]=value
        else:result[key]='[redacted structured value]'
    canonical(result,ceiling=8192)
    return result
