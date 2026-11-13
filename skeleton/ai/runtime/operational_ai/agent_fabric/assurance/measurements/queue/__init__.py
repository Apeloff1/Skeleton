"""Approved queue measurements and strict local lookup."""
ALLOWED=frozenset(('pending_pressure', 'oldest_wait_ms', 'running_occupancy', 'max_wait_ratio', 'per_tenant_share', 'throughput_per_sec', 'completion_ratio', 'held_ratio', 'retry_suppression_ratio', 'admission_rejection_rate', 'queue_turnover', 'worker_idle_ratio'))
def measure(name,observations):
    if type(name) is not str or name not in ALLOWED:
        raise ValueError('unknown measurement contract')
    if name == "pending_pressure":
        from . import pending_pressure as module
    elif name == "oldest_wait_ms":
        from . import oldest_wait_ms as module
    elif name == "running_occupancy":
        from . import running_occupancy as module
    elif name == "max_wait_ratio":
        from . import max_wait_ratio as module
    elif name == "per_tenant_share":
        from . import per_tenant_share as module
    elif name == "throughput_per_sec":
        from . import throughput_per_sec as module
    elif name == "completion_ratio":
        from . import completion_ratio as module
    elif name == "held_ratio":
        from . import held_ratio as module
    elif name == "retry_suppression_ratio":
        from . import retry_suppression_ratio as module
    elif name == "admission_rejection_rate":
        from . import admission_rejection_rate as module
    elif name == "queue_turnover":
        from . import queue_turnover as module
    elif name == "worker_idle_ratio":
        from . import worker_idle_ratio as module
    else:
        raise ValueError('unknown measurement contract')
    return module.measure(observations)
