"""Approved planning measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('completion_fraction', 'critical_path_share', 'parallelism_ratio', 'fanout_ratio', 'dependency_density', 'unavailable_step_fraction', 'tool_step_fraction', 'review_gate_fraction', 'unassigned_steps', 'longest_chain_ratio', 'plan_overrun_ratio', 'branch_count_density'))
_LOADERS = {
    "completion_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.completion_fraction"),
    "critical_path_share": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.critical_path_share"),
    "parallelism_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.parallelism_ratio"),
    "fanout_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.fanout_ratio"),
    "dependency_density": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.dependency_density"),
    "unavailable_step_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.unavailable_step_fraction"),
    "tool_step_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.tool_step_fraction"),
    "review_gate_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.review_gate_fraction"),
    "unassigned_steps": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.unassigned_steps"),
    "longest_chain_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.longest_chain_ratio"),
    "plan_overrun_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.plan_overrun_ratio"),
    "branch_count_density": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning.branch_count_density"),
}

def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=_LOADERS[name]()
    return module.measure(observations)
