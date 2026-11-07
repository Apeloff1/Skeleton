"""Approved queue measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('pending_pressure', 'oldest_wait_ms', 'running_occupancy', 'max_wait_ratio', 'per_tenant_share', 'throughput_per_sec', 'completion_ratio', 'held_ratio', 'retry_suppression_ratio', 'admission_rejection_rate', 'queue_turnover', 'worker_idle_ratio'))
_LOADERS = {
    "pending_pressure": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.pending_pressure"),
    "oldest_wait_ms": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.oldest_wait_ms"),
    "running_occupancy": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.running_occupancy"),
    "max_wait_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.max_wait_ratio"),
    "per_tenant_share": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.per_tenant_share"),
    "throughput_per_sec": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.throughput_per_sec"),
    "completion_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.completion_ratio"),
    "held_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.held_ratio"),
    "retry_suppression_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.retry_suppression_ratio"),
    "admission_rejection_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.admission_rejection_rate"),
    "queue_turnover": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.queue_turnover"),
    "worker_idle_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue.worker_idle_ratio"),
}

def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=_LOADERS[name]()
    return module.measure(observations)
