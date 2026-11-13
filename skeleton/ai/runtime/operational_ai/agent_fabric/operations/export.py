"""Privacy-preserving, hash-bound operator inventory export."""
from ..core.canonical import canonical,digest
from ..operations.doctor import inspect

def inventory(store,plan_id):
    proof=inspect(store,plan_id)
    plan,states,state=store.load(plan_id)
    public={'schema':'agent.inventory.v1','plan_id':plan_id,'plan_sha256':plan.sha256(),
            'state':state,'step_states':{k:v['state'] for k,v in sorted(states.items())},
            'proof':proof,'contains_model_text':False}
    return canonical(public,ceiling=131072)
