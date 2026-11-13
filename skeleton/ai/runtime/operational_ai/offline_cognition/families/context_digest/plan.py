"""context_digest: plan — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.planner import PlanTask,compile_plan
from skeleton.ai.runtime.operational_ai.offline_cognition.core.graph import topological
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import refuse
def compile(tasks):
    if type(tasks) not in (tuple,list) or any(type(t) is not PlanTask for t in tasks):
        refuse("typed dependency graph required")
    return compile_plan(tasks,max_tokens=PROFILE.context_limit)
def order(tasks):
    return topological([t.task_id for t in tasks],
                       [(dep,t.task_id) for t in tasks for dep in t.depends_on])
def executable():
    return {"plan_only":True,"model_directed_tools_allowed":False}
