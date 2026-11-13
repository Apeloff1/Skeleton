"""Canonical digest-bound tool outcomes and explicit side-effect status."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .spec import ToolError

@dataclass(frozen=True,slots=True)
class ToolExecutionReceipt:
    invocation_id:str
    spec_sha:str
    request_sha:str
    result_sha:str
    state:str
    output:dict
    duration_ns:int
    error:str|None=None

    @property
    def digest(self)->str:
        record={'invocation_id':self.invocation_id,'spec_sha':self.spec_sha,
                'request_sha':self.request_sha,'result_sha':self.result_sha,
                'state':self.state,'duration_ns':self.duration_ns,'error':self.error}
        return sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def __post_init__(self):
        if self.state not in {'succeeded','rejected','failed','uncertain'}:
            raise ToolError('receipt must have explicit finality')
        if type(self.duration_ns) is not int or self.duration_ns<0:
            raise ToolError('invalid tool duration')


def output_digest(output:dict)->str:
    try:b=json.dumps(output,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    except (TypeError,ValueError) as exc:raise ToolError('noncanonical tool result') from exc
    return sha256(b).hexdigest()
