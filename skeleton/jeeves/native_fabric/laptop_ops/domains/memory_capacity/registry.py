"""Eight-stage non-authoritative memory diagnostics, with exact field contracts."""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import model_footprint, kv_footprint, prompt_tokens, generation_tokens, remaining_disk, worker_slots, probe_age, pressure_override
DOMAIN = "memory_capacity"
STAGES = ("model_footprint", "kv_footprint", "prompt_tokens", "generation_tokens", "remaining_disk", "worker_slots", "probe_age", "pressure_override",)
STAGE_TYPES = (("model_footprint", "capacity"), ("kv_footprint", "capacity"), ("prompt_tokens", "bounded"), ("generation_tokens", "bounded"), ("remaining_disk", "capacity"), ("worker_slots", "capacity"), ("probe_age", "fresh"), ("pressure_override", "false"),)
HANDLERS = (model_footprint, kv_footprint, prompt_tokens, generation_tokens, remaining_disk, worker_slots, probe_age, pressure_override,)

def evaluate(evidence: object):
    """Every reserved resource dimension must be explicitly accounted for."""
    if type(evidence) is not dict or set(evidence) != set(STAGES):
        raise LaptopGateHold("memory capacity evidence incomplete or ambiguous")
    result = tuple(handler.check(evidence[stage]) for stage, handler in zip(STAGES, HANDLERS))
    if len(result) != len(STAGES):
        raise LaptopGateHold("missing memory safeguard")
    return result

def contracts():
    """Stable source contracts; never true native authorization."""
    return tuple(handler.contract() for handler in HANDLERS)
