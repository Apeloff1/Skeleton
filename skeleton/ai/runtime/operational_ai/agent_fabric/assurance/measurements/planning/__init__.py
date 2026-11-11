"""Approved planning measurements and strict local lookup."""
ALLOWED=frozenset(('completion_fraction', 'critical_path_share', 'parallelism_ratio', 'fanout_ratio', 'dependency_density', 'unavailable_step_fraction', 'tool_step_fraction', 'review_gate_fraction', 'unassigned_steps', 'longest_chain_ratio', 'plan_overrun_ratio', 'branch_count_density'))
def measure(name,observations):
    if type(name) is not str or name not in ALLOWED:
        raise ValueError('unknown measurement contract')
    if name == "completion_fraction":
        from . import completion_fraction as module
    elif name == "critical_path_share":
        from . import critical_path_share as module
    elif name == "parallelism_ratio":
        from . import parallelism_ratio as module
    elif name == "fanout_ratio":
        from . import fanout_ratio as module
    elif name == "dependency_density":
        from . import dependency_density as module
    elif name == "unavailable_step_fraction":
        from . import unavailable_step_fraction as module
    elif name == "tool_step_fraction":
        from . import tool_step_fraction as module
    elif name == "review_gate_fraction":
        from . import review_gate_fraction as module
    elif name == "unassigned_steps":
        from . import unassigned_steps as module
    elif name == "longest_chain_ratio":
        from . import longest_chain_ratio as module
    elif name == "plan_overrun_ratio":
        from . import plan_overrun_ratio as module
    elif name == "branch_count_density":
        from . import branch_count_density as module
    else:
        raise ValueError('unknown measurement contract')
    return module.measure(observations)
