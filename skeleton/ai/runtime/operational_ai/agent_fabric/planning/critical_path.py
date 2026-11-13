"""Deterministic weighted longest path; protects work budgets from fanout."""
from .dag import compile_plan
from ..core.canonical import uint
from ..core.errors import Invalid

def critical_path(plan,durations:dict[str,int]):
    order=compile_plan(plan)
    steps={s.step_id:s for s in plan.steps}
    if set(durations)!=set(steps):raise Invalid('missing duration estimates')
    costs={}
    parents={}
    for node in order:
        weight=uint(durations[node],'duration',0,86400000)
        deps=steps[node].depends_on
        predecessor=max(deps,key=lambda d:(costs[d],d)) if deps else None
        costs[node]=weight+(costs[predecessor] if predecessor else 0)
        parents[node]=predecessor
    last=max(order,key=lambda d:(costs[d],d))
    path=[]
    while last is not None:path.append(last);last=parents[last]
    return {'duration_ms':max(costs.values()),'path':tuple(reversed(path))}
