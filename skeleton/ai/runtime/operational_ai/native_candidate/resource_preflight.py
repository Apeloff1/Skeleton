"""Conservative working-set estimate before allocating a cloned native model."""
from __future__ import annotations
from .run_limits import ResourceLimits
from .plan import TrainingPlan
from .preflight import TrainingAdmission
from .errors import deny


def estimate(champion, plan: TrainingPlan, admission: TrainingAdmission,
             limits: ResourceLimits | None = None) -> dict:
    if not hasattr(champion, "model_bytes") or not hasattr(champion, "limits"):
        deny("resource-native-model")
    if type(plan) is not TrainingPlan or type(admission) is not TrainingAdmission:
        deny("resource-contract")
    limits = limits or ResourceLimits()
    # CPU reference implementation retains a full clone, gradients and caches.
    # Conservative memory forecast is a policy hold, not measured RSS.
    base = champion.model_bytes
    working_estimate = base * 8 + (admission.tokens.total_tokens * 128)
    proof = limits.admit(
        model_bytes=base, steps=admission.tokens.optimizer_steps_estimate,
        examples=admission.tokens.lines,
        estimated_working_bytes=working_estimate,
    )
    return {
        **proof, "working_set_is_estimate": True,
        "actual_device_memory_measured": False,
        "model_clone_required": True,
    }
