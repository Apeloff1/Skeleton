"""Content-addressed checkpoint of deterministic intermediate workflow outcomes."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .graph import WorkflowError

@dataclass(frozen=True,slots=True)
class Checkpoint:
    workflow_id:str
    step_id:str
    version:int
    input_sha:str
    output_sha:str
    result:dict


def seal(workflow_id:str,step_id:str,input_record:dict,result:dict,*,version:int=1)->Checkpoint:
    if type(version) is not int or not 1<=version<=1_000_000:raise WorkflowError('invalid checkpoint revision')
    def digest(x):return sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return Checkpoint(workflow_id,step_id,version,digest(input_record),digest(result),result)


def verify(checkpoint:Checkpoint,input_record:dict)->bool:
    expected=seal(checkpoint.workflow_id,checkpoint.step_id,input_record,checkpoint.result,version=checkpoint.version)
    return checkpoint==expected
