"""Dependency blast-radius for safe plan edits and revocation."""
from .dag import compile_plan

def descendants(plan,node):
    order=compile_plan(plan)
    if node not in order:raise ValueError('unknown plan node')
    impacts={node}
    for name in order:
        s=next(s for s in plan.steps if s.step_id==name)
        if any(d in impacts for d in s.depends_on):impacts.add(name)
    return tuple(n for n in order if n in impacts and n!=node)

def ancestors(plan,node):
    order=compile_plan(plan)
    if node not in order:raise ValueError('unknown plan node')
    known={node}
    for name in reversed(order):
        if name in known:
            known.update(next(s.depends_on for s in plan.steps if s.step_id==name))
    return tuple(n for n in order if n in known and n!=node)
