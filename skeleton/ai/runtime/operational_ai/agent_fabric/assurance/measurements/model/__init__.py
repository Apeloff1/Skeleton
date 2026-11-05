"""Approved model measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('memory_available_margin', 'vram_headroom', 'kv_cache_bytes_per_token', 'batch_utilization', 'token_budget_left', 'loader_duplication_bytes', 'active_model_ratio', 'host_reserve_ratio', 'shard_integrity_fraction', 'tokenizer_mismatch_count', 'setup_latency_per_gb', 'workers_per_model'))
def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=import_module('skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.'+name)
    return module.measure(observations)
