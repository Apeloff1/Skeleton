"""Cross-stage context packing diagnostics before operator-approved GGUF use.

No untrusted input, source-only observation or model text can override
the installed model context window or reserve a native token budget.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    model_context,
    prompt_tokens,
    output_reservation,
    role_integrity,
    session_window,
    system_message,
    truncation_permission,
    context_revision,
)

DOMAIN = "context_window"
STAGES = ("model_context", "prompt_tokens", "output_reservation", "role_integrity", "session_window", "system_message", "truncation_permission", "context_revision",)
STAGE_TYPES = (("model_context", "capacity"), ("prompt_tokens", "bounded"), ("output_reservation", "capacity"), ("role_integrity", "sha_equal"), ("session_window", "bounded"), ("system_message", "true"), ("truncation_permission", "false"), ("context_revision", "monotonic"),)
HANDLERS = (model_context, prompt_tokens, output_reservation, role_integrity, session_window, system_message, truncation_permission, context_revision,)


def evaluate(evidence: object):
    """Ensure prompt and output fit a single finite model context."""
    if type(evidence) is not dict or set(evidence) != set(STAGES):
        raise LaptopGateHold("incomplete context admission contract")
    stage_results = tuple(handler.check(evidence[name])
                          for name, handler in zip(STAGES, HANDLERS))
    if len(stage_results) != 8:
        raise LaptopGateHold("context stage inventory incomplete")
    # Individual stages may fail normally; preserve their explicit denials.
    # After they pass, still reject cross-field resource inconsistencies.
    if all(result.accepted for result in stage_results):
        prompt = evidence["prompt_tokens"]["used"]
        reserved = evidence["output_reservation"]["reserved"]
        capacity = evidence["model_context"]["available"]
        if prompt + reserved > capacity:
            raise LaptopGateHold("prompt and reserved generation exceed context")
    return stage_results


def contracts() -> tuple[dict[str, object], ...]:
    return tuple(handler.contract() for handler in HANDLERS)
