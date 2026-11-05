"""Source-bound request dedupe fingerprints distinct from unsafe model guesses."""
from __future__ import annotations
import json
from hashlib import sha256
from .contracts import Request


def fingerprint(request:Request,model_digest:str)->str:
    data={'tenant':request.tenant,'request':request.request_id,'messages':request.messages,
        'seed':request.seed,'temperature':request.temperature,'max_tokens':request.max_tokens,
        'model':model_digest}
    return sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
