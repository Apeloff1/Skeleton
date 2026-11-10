"""Approved planning measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('completion_fraction', 'critical_path_share', 'parallelism_ratio', 'fanout_ratio', 'dependency_density', 'unavailable_step_fraction', 'tool_step_fraction', 'review_gate_fraction', 'unassigned_steps', 'longest_chain_ratio', 'plan_overrun_ratio', 'branch_count_density'))
def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=import_module('skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.'+name)
    return module.measure(observations)
