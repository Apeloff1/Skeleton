"""Read-only detection of uncertain work and operator-only resumptions."""
from ..core.errors import Held
from ..operations.doctor import inspect

def review(store,plan_id):
    plan,steps,state=store.load(plan_id)
    running=tuple(k for k,v in steps.items() if v['state']=='running')
    held=tuple(k for k,v in steps.items() if v['state']=='held')
    return {'status':state,'running_uncertain':running,'held':held,
            'automatic_retry_accepted':False,'requires_operator':bool(running or held)}

def reconcile_model_only(store,plan_id,step_id,*,operator_approved=False):
    if operator_approved is not True:raise Held('independent operator required')
    plan,steps,state=store.load(plan_id)
    if steps[step_id]['state']!='held':raise Held('only explicitly held work eligible')
    return store.repair(plan_id,step_id,approved=True)
