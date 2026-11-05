"""Check a model-bound first Jeeves turn has enough shared context for prompt and output.

This typed source inventory cannot bypass the canonical native model loader.
No accepted synthetic observation is an actual release certification.
"""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    model_context,
    prompt_tokens,
    generation_reservation,
    installed_source,
    session_bound,
    user_owner,
    run_sequence,
    unconfirmed_effect,
)

DOMAIN = "first_turn"
STAGES = ("model_context", "prompt_tokens", "generation_reservation", "installed_source", "session_bound", "user_owner", "run_sequence", "unconfirmed_effect",)
STAGE_TYPES = (("model_context", "capacity"), ("prompt_tokens", "bounded"), ("generation_reservation", "capacity"), ("installed_source", "sha_equal"), ("session_bound", "true"), ("user_owner", "same_owner"), ("run_sequence", "monotonic"), ("unconfirmed_effect", "false"),)
HANDLERS = (model_context, prompt_tokens, generation_reservation, installed_source, session_bound, user_owner, run_sequence, unconfirmed_effect,)


def evaluate(e: object):
    """Reject incomplete safeguards and inconsistent cross-stage evidence."""
    if type(e) is not dict or set(e) != set(STAGES):
        raise LaptopGateHold("incomplete first_turn source contract")
    result = tuple(handler.check(e[label])
                   for label,handler in zip(STAGES,HANDLERS))
    if len(result) != 8 or len({r.stage for r in result}) != 8:
        raise LaptopGateHold("incomplete first_turn safeguard verdict")
    if all(r.accepted for r in result) and not (e["prompt_tokens"]["used"] + e["generation_reservation"]["reserved"] <= e["model_context"]["available"]):
        raise LaptopGateHold("cross-stage first_turn source contradiction")
    return result


def contracts() -> tuple[dict[str, object], ...]:
    """Source shape only; real device and release witnesses are separate."""
    return tuple(handler.contract() for handler in HANDLERS)


__all__ = ["STAGES", "STAGE_TYPES", "evaluate", "contracts"]
