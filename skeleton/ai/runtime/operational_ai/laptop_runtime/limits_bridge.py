"""Map exact authoritative SpineLimits to non-escalating local transport budgets."""
from __future__ import annotations
from .contracts import nonnegative,refuse

def describe(limits):
    required=("input_bytes","response_bytes","max_output_tokens",
              "context_tokens","deadline_ms","max_pending","max_history","max_sources")
    if any(not hasattr(limits,x) for x in required):
        refuse("complete real SpineLimits required")
    raw={name:getattr(limits,name) for name in required}
    for name,value in raw.items():
        nonnegative(value,maximum=2_097_152)
    if raw["max_output_tokens"]>=raw["context_tokens"]:
        refuse("output token request exceeds context window")
    return {"schema":"laptop-bounded-limits.v1","limits":raw,
            "client_may_raise_limits":False}
