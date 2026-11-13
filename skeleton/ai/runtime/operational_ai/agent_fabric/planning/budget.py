"""Deterministic allocation of finite output-token budgets over a plan."""
from .dag import compile_plan
from ..core.canonical import uint
from ..core.errors import Exhausted

def allocate(plan,total:int,*,floor:int=16):
    uint(total,'total tokens',1,1048576);uint(floor,'token floor',1,8192)
    order=compile_plan(plan)
    model=[s.step_id for s in plan.steps if s.kind=='model']
    if len(model)*floor>total:raise Exhausted('plan exceeds model-token budget')
    if not model:return {}
    share,extra=divmod(total-len(model)*floor,len(model))
    return {k:floor+share+(1 if i<extra else 0) for i,k in enumerate(sorted(model))}
