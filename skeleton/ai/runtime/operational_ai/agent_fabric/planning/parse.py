"""Strict plan JSON parsing. A model proposal is never an authorization."""
from ..core.canonical import parse,canonical
from ..core.errors import Invalid
from .spec import Plan,Step
from .dag import compile_plan

def decode(raw:bytes):
    v=parse(raw,ceiling=2097152)
    if not isinstance(v,dict) or set(v)!={'schema','id','session','purpose','steps'} or v['schema']!='agent.plan.v1':raise Invalid('invalid plan envelope')
    if not isinstance(v['steps'],list) or not v['steps']:raise Invalid('invalid steps')
    steps=[]
    for s in v['steps']:
        if not isinstance(s,dict) or set(s)!={'id','kind','instruction','depends_on','resource'} or not isinstance(s['depends_on'],list):raise Invalid('invalid step schema')
        steps.append(Step(s['id'],s['kind'],s['instruction'],tuple(s['depends_on']),s['resource']))
    plan=Plan(v['id'],v['session'],tuple(steps),v['purpose'])
    compile_plan(plan)
    if canonical(plan.record(),ceiling=2097152)!=raw:raise Invalid('noncanonical plan representation')
    return plan

def encode(plan:Plan)->bytes:
    compile_plan(plan)
    return canonical(plan.record(),ceiling=2097152)
