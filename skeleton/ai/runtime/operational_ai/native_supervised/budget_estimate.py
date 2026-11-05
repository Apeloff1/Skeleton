"""Conservative CPU SFT work forecast; never invent measured throughput."""
from __future__ import annotations
from .target_plan import TargetPlan
from .policy import SupervisedPolicy
from .errors import reject


def forecast(plan:TargetPlan,policy:SupervisedPolicy)->dict:
    if type(plan) is not TargetPlan or type(policy) is not SupervisedPolicy:
        reject("budget-forecast-contract")
    predicted_updates=plan.total_optimizer_steps
    if predicted_updates>policy.max_optimizer_steps:
        reject("forecast-optimizer-exceeded")
    token_attention_upper=predicted_updates*policy.context*policy.layers
    return {
        "schema":"skeleton.native-supervised.compute-forecast.v1",
        "optimizer_updates":predicted_updates,
        "context_upper":policy.context,
        "attention_window_work_upper":token_attention_upper,
        "estimated_not_actual":True,
        "actual_training_wall_ms":None,
        "actual_hardware_peak_rss":None,
        "unbounded_background_work":False,
        "device_qualified":False,
    }
