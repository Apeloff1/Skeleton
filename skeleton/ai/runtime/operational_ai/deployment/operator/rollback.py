"""Content-addressed release rollback intention; never mutate active state implicitly."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,re

@dataclass(frozen=True,slots=True)
class RollbackPlan:
    release_id:str
    previous_model_sha:str
    current_model_sha:str
    current_schema:int
    previous_schema:int
    maintenance_required:bool
    digest:str


def plan_rollback(release_id:str,previous_sha:str,current_sha:str,
                  current_schema:int,previous_schema:int)->RollbackPlan:
    pattern=re.compile(r'^[0-9a-f]{64}$')
    if not all(pattern.fullmatch(x) for x in (previous_sha,current_sha)):
        raise ValueError('rollback model digests must be pinned')
    if type(current_schema) is not int or type(previous_schema) is not int or min(current_schema,previous_schema)<1:
        raise ValueError('invalid durable schema revisions')
    if current_schema<previous_schema:
        raise ValueError('cannot rollback to future schema')
    if not release_id or len(release_id)>128:raise ValueError('invalid release ID')
    maintenance=current_schema!=previous_schema
    material=[release_id,previous_sha,current_sha,current_schema,previous_schema,maintenance]
    digest=sha256(json.dumps(material,separators=(',',':')).encode()).hexdigest()
    return RollbackPlan(release_id,previous_sha,current_sha,current_schema,previous_schema,maintenance,digest)
