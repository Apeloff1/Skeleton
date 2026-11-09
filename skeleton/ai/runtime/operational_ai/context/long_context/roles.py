"""Strict role remapping: source content never becomes system instruction."""
from __future__ import annotations
from .contracts import Span,ContextError


def model_role(span:Span)->str:
    if span.trust=='system':return 'system'
    if span.trust in {'user','retrieved','tool_result'}:return 'user'
    if span.trust=='assistant':return 'assistant'
    raise ContextError('invalid context role')


def role_priority(trust:str)->int:
    ranks={'system':0,'user':1,'assistant':2,'retrieved':3,'tool_result':4}
    if trust not in ranks:raise ContextError('unknown trust label')
    return ranks[trust]
