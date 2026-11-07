"""Approved context measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('retained_turns_fraction', 'dropped_turns', 'source_bytes_fraction', 'context_occupancy', 'citation_rate', 'prompt_overhead', 'model_output_reserve', 'source_relevance_gap', 'available_token_margin', 'duplicate_source_fraction', 'trusted_source_ratio', 'context_estimate_divergence'))
_LOADERS = {
    "retained_turns_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.retained_turns_fraction"),
    "dropped_turns": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.dropped_turns"),
    "source_bytes_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.source_bytes_fraction"),
    "context_occupancy": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.context_occupancy"),
    "citation_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.citation_rate"),
    "prompt_overhead": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.prompt_overhead"),
    "model_output_reserve": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.model_output_reserve"),
    "source_relevance_gap": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.source_relevance_gap"),
    "available_token_margin": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.available_token_margin"),
    "duplicate_source_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.duplicate_source_fraction"),
    "trusted_source_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.trusted_source_ratio"),
    "context_estimate_divergence": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context.context_estimate_divergence"),
}

def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=_LOADERS[name]()
    return module.measure(observations)
