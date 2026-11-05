"""finite_metrics: model-evidence review facade with independently supplied inputs."""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import refuse
from skeleton.ai.runtime.operational_ai.offline_cognition.core.quality_gate import (
    BenchmarkBinding,LatencySample,evaluate_exact,distribution,inspect_envelope,
    verify_reply_evidence,refusal_statistics,guarded_review,
)

def evaluate(binding,cases,*,min_cases=100,min_lower_bound=0.95):
    return evaluate_exact(binding,cases,min_cases=min_cases,
                          min_lower_bound=min_lower_bound)

def latencies(rows,*,min_samples=100):
    return distribution(rows,min_samples=min_samples)

def response(payload,*,schema):
    if type(payload) is not bytes or len(payload)>PROFILE.byte_limit:
        refuse("quality envelope exceeds declared original byte ceiling")
    return inspect_envelope(payload,expected_schema=schema)

def grounding(native_receipt,index,spans,*,required=True):
    return verify_reply_evidence(native_receipt,index,spans,
                                 grounding_required=required)

def refusal_scores(rows):
    return refusal_statistics(rows)

def review(binding,benchmark,latencies,grounding,*,threshold=0.95):
    return guarded_review(binding,benchmark,latencies,grounding,
                          benchmark_threshold=threshold)

def assurance():
    return {"family":PROFILE.name,"evaluator_identity_declared":True,
            "independent_evaluator_executed_here":False,
            "semantics_independently_verified_here":False,
            "model_auto_promotion":False,"release_certified":False}
