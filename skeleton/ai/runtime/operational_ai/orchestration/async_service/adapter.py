"""Stable request/result projection for the loopback HTTP operation dispatcher."""
from __future__ import annotations
from ...persistence.durable.database import DurableError
from .executor import AsyncAIExecutor


def dispatch(executor:AsyncAIExecutor,operation:str,payload:dict)->dict:
    if not isinstance(payload,dict):raise DurableError('AI dispatcher requires object')
    if operation=='ai.async.submit':
        if set(payload)-{'session','request_id','question','seed','temperature'} or not {'session','request_id','question'}.issubset(payload):
            raise DurableError('invalid async submit payload')
        job=executor.submit(session=payload['session'],request_id=payload['request_id'],
                question=payload['question'],seed=payload.get('seed',0),
                temperature=payload.get('temperature',1.0))
        return job.__dict__ if hasattr(job,'__dict__') else {f:getattr(job,f) for f in job.__dataclass_fields__}
    if operation=='ai.async.status':
        if set(payload)!={'request_id'}:raise DurableError('invalid async status payload')
        job=executor.get(payload['request_id'])
        return {f:getattr(job,f) for f in job.__dataclass_fields__}
    if operation=='ai.async.cancel':
        if set(payload)!={'request_id'}:raise DurableError('invalid async cancellation payload')
        job=executor.cancel(payload['request_id'])
        return {f:getattr(job,f) for f in job.__dataclass_fields__}
    raise DurableError('unknown AI async operation')
