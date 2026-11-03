"""Typed, authoritatively validated command entrypoint without network exposure."""
from __future__ import annotations
from ..core.canonical import identifier,parse,canonical
from ..core.errors import Invalid
from ..planning.parse import decode
from ..operations.doctor import inspect
ALLOWED=frozenset(('submit','inspect','ready','run_one'))
def dispatch(fabric,payload:bytes):
    command=parse(payload,ceiling=2097152)
    if not isinstance(command,dict) or set(command)!={'schema','operation','arguments'}:
        raise Invalid('invalid agent command envelope')
    if command['schema']!='agent.command.v1' or command['operation'] not in ALLOWED or not isinstance(command['arguments'],dict):
        raise Invalid('unsupported operation')
    op=command['operation'];args=command['arguments']
    if op=='submit':
        if set(args)!={'plan'} or not isinstance(args['plan'],dict):raise Invalid('invalid plan submission')
        return fabric.submit(decode(canonical(args['plan'],ceiling=2097152)))
    if set(args)!={'plan_id'}:raise Invalid('bounded plan selector required')
    pid=identifier(args['plan_id'],'plan')
    if op=='inspect':return inspect(fabric.store,pid)
    if op=='ready':return {'ready':list(fabric.next(pid))}
    return fabric.run_one(pid)
