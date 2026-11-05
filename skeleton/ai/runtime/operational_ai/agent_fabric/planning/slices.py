"""Dependency-closed bounded workflow slices for reviewable work packages."""
from .dag import compile_plan
from ..core.canonical import uint
from ..core.errors import Invalid

def slice_plan(plan,*,limit:int=32):
    uint(limit,'slice limit',1,1024)
    order=compile_plan(plan)
    lookup={s.step_id:s for s in plan.steps}
    bins=[];batch=[];done=set()
    for node in order:
        if len(batch)>=limit:bins.append(tuple(batch));done.update(batch);batch=[]
        if not set(lookup[node].depends_on)<=done.union(batch):raise Invalid('slice violates dependencies')
        batch.append(node)
    if batch:bins.append(tuple(batch))
    return tuple(bins)
