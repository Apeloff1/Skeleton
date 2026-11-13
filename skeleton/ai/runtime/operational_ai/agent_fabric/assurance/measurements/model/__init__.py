"""Approved model measurements and strict local lookup."""
ALLOWED=frozenset(('memory_available_margin', 'vram_headroom', 'kv_cache_bytes_per_token', 'batch_utilization', 'token_budget_left', 'loader_duplication_bytes', 'active_model_ratio', 'host_reserve_ratio', 'shard_integrity_fraction', 'tokenizer_mismatch_count', 'setup_latency_per_gb', 'workers_per_model'))
def measure(name,observations):
    if type(name) is not str or name not in ALLOWED:
        raise ValueError('unknown measurement contract')
    if name == "memory_available_margin":
        from . import memory_available_margin as module
    elif name == "vram_headroom":
        from . import vram_headroom as module
    elif name == "kv_cache_bytes_per_token":
        from . import kv_cache_bytes_per_token as module
    elif name == "batch_utilization":
        from . import batch_utilization as module
    elif name == "token_budget_left":
        from . import token_budget_left as module
    elif name == "loader_duplication_bytes":
        from . import loader_duplication_bytes as module
    elif name == "active_model_ratio":
        from . import active_model_ratio as module
    elif name == "host_reserve_ratio":
        from . import host_reserve_ratio as module
    elif name == "shard_integrity_fraction":
        from . import shard_integrity_fraction as module
    elif name == "tokenizer_mismatch_count":
        from . import tokenizer_mismatch_count as module
    elif name == "setup_latency_per_gb":
        from . import setup_latency_per_gb as module
    elif name == "workers_per_model":
        from . import workers_per_model as module
    else:
        raise ValueError('unknown measurement contract')
    return module.measure(observations)
