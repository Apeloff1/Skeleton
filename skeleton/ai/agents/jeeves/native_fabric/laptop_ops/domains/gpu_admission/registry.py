"""Bound requested local GPU offload layers by observed accelerator reservation.

All eight source-only observations are required. Consistent synthetic input
is never proof of a real running model, source license or physical device.
"""
from __future__ import annotations
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    driver_observed,
    gpu_memory,
    offload_layers,
    queue_slots,
    device_owner,
    telemetry_epoch,
    device_observation,
    unverified_fallback,
)

DOMAIN = "gpu_admission"
STAGES = ("driver_observed", "gpu_memory", "offload_layers", "queue_slots", "device_owner", "telemetry_epoch", "device_observation", "unverified_fallback",)
STAGE_TYPES = (("driver_observed", "true"), ("gpu_memory", "capacity"), ("offload_layers", "bounded"), ("queue_slots", "capacity"), ("device_owner", "same_owner"), ("telemetry_epoch", "monotonic"), ("device_observation", "fresh"), ("unverified_fallback", "false"),)
HANDLERS = (driver_observed, gpu_memory, offload_layers, queue_slots, device_owner, telemetry_epoch, device_observation, unverified_fallback,)


def evaluate(evidence: object):
    """Fail closed on missing stages and mutually inconsistent source claims."""
    if type(evidence) is not dict or set(evidence) != set(STAGES):
        raise LaptopGateHold("missing or extra gpu_admission source safeguard")
    observed = tuple(handler.check(evidence[stage])
                     for stage, handler in zip(STAGES, HANDLERS))
    if len(observed) != 8 or len({item.stage for item in observed}) != 8:
        raise LaptopGateHold("incomplete gpu_admission stage inventory")
    if all(item.accepted for item in observed) and not (evidence["offload_layers"]["used"] <= evidence["gpu_memory"]["reserved"]):
        raise LaptopGateHold("inconsistent gpu_admission cross-stage facts")
    return observed


def contracts() -> tuple[dict[str, object], ...]:
    """Publish stable stage input inventory, not native startup authorization."""
    return tuple(handler.contract() for handler in HANDLERS)


__all__ = ["evaluate", "contracts", "STAGES", "STAGE_TYPES"]
