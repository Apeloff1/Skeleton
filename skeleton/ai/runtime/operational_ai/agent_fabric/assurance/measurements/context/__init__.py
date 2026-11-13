"""Approved context measurements and strict local lookup."""
ALLOWED=frozenset(('retained_turns_fraction', 'dropped_turns', 'source_bytes_fraction', 'context_occupancy', 'citation_rate', 'prompt_overhead', 'model_output_reserve', 'source_relevance_gap', 'available_token_margin', 'duplicate_source_fraction', 'trusted_source_ratio', 'context_estimate_divergence'))
def measure(name,observations):
    if type(name) is not str or name not in ALLOWED:
        raise ValueError('unknown measurement contract')
    if name == "retained_turns_fraction":
        from . import retained_turns_fraction as module
    elif name == "dropped_turns":
        from . import dropped_turns as module
    elif name == "source_bytes_fraction":
        from . import source_bytes_fraction as module
    elif name == "context_occupancy":
        from . import context_occupancy as module
    elif name == "citation_rate":
        from . import citation_rate as module
    elif name == "prompt_overhead":
        from . import prompt_overhead as module
    elif name == "model_output_reserve":
        from . import model_output_reserve as module
    elif name == "source_relevance_gap":
        from . import source_relevance_gap as module
    elif name == "available_token_margin":
        from . import available_token_margin as module
    elif name == "duplicate_source_fraction":
        from . import duplicate_source_fraction as module
    elif name == "trusted_source_ratio":
        from . import trusted_source_ratio as module
    elif name == "context_estimate_divergence":
        from . import context_estimate_divergence as module
    else:
        raise ValueError('unknown measurement contract')
    return module.measure(observations)
