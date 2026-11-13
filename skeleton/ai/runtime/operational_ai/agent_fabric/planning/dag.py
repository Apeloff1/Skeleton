"""Deterministic DAG compilation and cycle detection, no model-assigned priority."""
from __future__ import annotations
from .spec import Plan
from ..core.errors import Invalid
from ..core.limits import Limits

def compile_plan(plan:Plan,limits:Limits|None=None)->tuple[str,...]:
    limits=limits or Limits()
    if len(plan.steps)>limits.steps:raise Invalid('step limit exceeded')
    records={s.step_id:s for s in plan.steps}
    for s in plan.steps:
        if len(s.depends_on)>limits.dependencies:raise Invalid('dependency limit exceeded')
        if s.step_id in s.depends_on or any(dep not in records for dep in s.depends_on):raise Invalid('dangling or reflexive plan edge')
    incoming={s.step_id:set(s.depends_on) for s in plan.steps}
    order=[];available=sorted(key for key,deps in incoming.items() if not deps)
    while available:
        next_id=available.pop(0);order.append(next_id)
        for node in sorted(incoming):
            if next_id in incoming[node]:
                incoming[node].remove(next_id)
                if not incoming[node] and node not in order and node not in available:
                    available.append(node);available.sort()
    if len(order)!=len(records):raise Invalid('cyclic plan')
    return tuple(order)

def ready(plan:Plan,completed:set[str],active:set[str]=frozenset())->tuple[str,...]:
    order=compile_plan(plan)
    by_id={s.step_id:s for s in plan.steps}
    return tuple(step for step in order if step not in completed and step not in active and set(by_id[step].depends_on)<=completed)
