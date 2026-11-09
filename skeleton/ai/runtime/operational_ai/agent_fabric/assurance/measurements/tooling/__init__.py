"""Approved tooling measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('accepted_call_ratio', 'effect_ambiguity_ratio', 'approval_consumption_fraction', 'budget_utilization', 'execution_latency', 'sandbox_denial_ratio', 'side_effect_rate', 'explicit_denial_fraction', 'timeout_fraction', 'tool_result_size_ratio', 'idempotent_reply_fraction', 'human_review_ratio'))
def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=import_module('skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling.'+name)
    return module.measure(observations)
