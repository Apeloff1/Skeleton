"""Approved tooling measurements and strict local lookup."""
ALLOWED=frozenset(('accepted_call_ratio', 'effect_ambiguity_ratio', 'approval_consumption_fraction', 'budget_utilization', 'execution_latency', 'sandbox_denial_ratio', 'side_effect_rate', 'explicit_denial_fraction', 'timeout_fraction', 'tool_result_size_ratio', 'idempotent_reply_fraction', 'human_review_ratio'))
def measure(name,observations):
    if type(name) is not str or name not in ALLOWED:
        raise ValueError('unknown measurement contract')
    if name == "accepted_call_ratio":
        from . import accepted_call_ratio as module
    elif name == "effect_ambiguity_ratio":
        from . import effect_ambiguity_ratio as module
    elif name == "approval_consumption_fraction":
        from . import approval_consumption_fraction as module
    elif name == "budget_utilization":
        from . import budget_utilization as module
    elif name == "execution_latency":
        from . import execution_latency as module
    elif name == "sandbox_denial_ratio":
        from . import sandbox_denial_ratio as module
    elif name == "side_effect_rate":
        from . import side_effect_rate as module
    elif name == "explicit_denial_fraction":
        from . import explicit_denial_fraction as module
    elif name == "timeout_fraction":
        from . import timeout_fraction as module
    elif name == "tool_result_size_ratio":
        from . import tool_result_size_ratio as module
    elif name == "idempotent_reply_fraction":
        from . import idempotent_reply_fraction as module
    elif name == "human_review_ratio":
        from . import human_review_ratio as module
    else:
        raise ValueError('unknown measurement contract')
    return module.measure(observations)
