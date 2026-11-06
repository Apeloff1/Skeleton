"""Approved model measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('memory_available_margin', 'vram_headroom', 'kv_cache_bytes_per_token', 'batch_utilization', 'token_budget_left', 'loader_duplication_bytes', 'active_model_ratio', 'host_reserve_ratio', 'shard_integrity_fraction', 'tokenizer_mismatch_count', 'setup_latency_per_gb', 'workers_per_model'))
_LOADERS = {
    "memory_available_margin": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.memory_available_margin"),
    "vram_headroom": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.vram_headroom"),
    "kv_cache_bytes_per_token": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.kv_cache_bytes_per_token"),
    "batch_utilization": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.batch_utilization"),
    "token_budget_left": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.token_budget_left"),
    "loader_duplication_bytes": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.loader_duplication_bytes"),
    "active_model_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.active_model_ratio"),
    "host_reserve_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.host_reserve_ratio"),
    "shard_integrity_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.shard_integrity_fraction"),
    "tokenizer_mismatch_count": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.tokenizer_mismatch_count"),
    "setup_latency_per_gb": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.setup_latency_per_gb"),
    "workers_per_model": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model.workers_per_model"),
}

def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=_LOADERS[name]()
    return module.measure(observations)
