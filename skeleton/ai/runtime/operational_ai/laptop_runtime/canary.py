"""Explicit real inference canary, not a generated pseudo-model quality score."""
from __future__ import annotations
from .contracts import nonnegative,refuse

def run_native_canary(worker,*,seed=32,approve=False):
    if approve is not True:
        refuse("native inference canary requires explicit operator request")
    seed=nonnegative(seed,maximum=2**32-1)
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.qualification import run_canary
    result=run_canary(worker.spine.backend,worker.spine.identity,
                      worker.spine.limits,seed=seed)
    if result.get("status")!="native-canary-executed-not-quality-certified":
        refuse("live canary did not provide honest native status")
    return result
