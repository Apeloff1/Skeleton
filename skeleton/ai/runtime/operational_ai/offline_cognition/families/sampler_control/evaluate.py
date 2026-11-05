"""sampler_control: evaluate — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.evaluation import EvaluationCase,evaluate,wilson_lower
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import refuse
def run(cases,*,min_lower=0):
    if type(cases) not in (tuple,list) or len(cases)>100000:
        refuse("finite independently supplied evaluation batch")
    if any(type(c) is not EvaluationCase for c in cases):
        refuse("typed and hash-bound benchmark data required")
    return evaluate(cases,min_cases=PROFILE.min_evidence,min_lower_bound=min_lower)
def confidence(successes,total):
    return wilson_lower(successes,total)
