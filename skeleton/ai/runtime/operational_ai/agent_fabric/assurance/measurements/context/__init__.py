"""Approved context measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('retained_turns_fraction', 'dropped_turns', 'source_bytes_fraction', 'context_occupancy', 'citation_rate', 'prompt_overhead', 'model_output_reserve', 'source_relevance_gap', 'available_token_margin', 'duplicate_source_fraction', 'trusted_source_ratio', 'context_estimate_divergence'))
def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=import_module('skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.'+name)
    return module.measure(observations)
