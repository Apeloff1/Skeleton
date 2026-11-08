"""Approved tooling measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('accepted_call_ratio', 'effect_ambiguity_ratio', 'approval_consumption_fraction', 'budget_utilization', 'execution_latency', 'sandbox_denial_ratio', 'side_effect_rate', 'explicit_denial_fraction', 'timeout_fraction', 'tool_result_size_ratio', 'idempotent_reply_fraction', 'human_review_ratio'))
_LOADERS = {
    "accepted_call_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.accepted_call_ratio"),
    "effect_ambiguity_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.effect_ambiguity_ratio"),
    "approval_consumption_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.approval_consumption_fraction"),
    "budget_utilization": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.budget_utilization"),
    "execution_latency": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.execution_latency"),
    "sandbox_denial_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.sandbox_denial_ratio"),
    "side_effect_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.side_effect_rate"),
    "explicit_denial_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.explicit_denial_fraction"),
    "timeout_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.timeout_fraction"),
    "tool_result_size_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.tool_result_size_ratio"),
    "idempotent_reply_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.idempotent_reply_fraction"),
    "human_review_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.human_review_ratio"),
}

def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=_LOADERS[name]()
    return module.measure(observations)
