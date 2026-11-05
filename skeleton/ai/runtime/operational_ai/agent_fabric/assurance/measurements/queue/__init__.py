"""Approved queue measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('pending_pressure', 'oldest_wait_ms', 'running_occupancy', 'max_wait_ratio', 'per_tenant_share', 'throughput_per_sec', 'completion_ratio', 'held_ratio', 'retry_suppression_ratio', 'admission_rejection_rate', 'queue_turnover', 'worker_idle_ratio'))
def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=import_module('skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.'+name)
    return module.measure(observations)
