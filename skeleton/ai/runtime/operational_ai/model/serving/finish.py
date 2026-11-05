"""Normalize native stop reasons without converting failures into success."""
from __future__ import annotations
from .contracts import ServingError

STOP={'stop','eos','eos_token','end_turn'}
TRUNC={'length','max_tokens','context_limit'}


def finish_class(reason:str)->str:
    if reason in STOP:return 'complete'
    if reason in TRUNC:return 'truncated'
    if reason in {'cancelled','deadline'}:return 'aborted'
    raise ServingError('unknown model finish semantics')
