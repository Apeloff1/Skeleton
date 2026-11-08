"""Approved deployment measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('install_complete_fraction', 'missing_shard_fraction', 'verified_bytes_ratio', 'daemon_uptime', 'restart_success_ratio', 'memory_pressure_ratio', 'startup_held_ratio', 'manifest_completeness', 'health_probe_success_ratio', 'canary_pass_rate', 'device_coverage', 'native_e2e_coverage'))
_LOADERS = {
    "install_complete_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.install_complete_fraction"),
    "missing_shard_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.missing_shard_fraction"),
    "verified_bytes_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.verified_bytes_ratio"),
    "daemon_uptime": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.daemon_uptime"),
    "restart_success_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.restart_success_ratio"),
    "memory_pressure_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.memory_pressure_ratio"),
    "startup_held_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.startup_held_ratio"),
    "manifest_completeness": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.manifest_completeness"),
    "health_probe_success_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.health_probe_success_ratio"),
    "canary_pass_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.canary_pass_rate"),
    "device_coverage": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.device_coverage"),
    "native_e2e_coverage": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.native_e2e_coverage"),
}

def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=_LOADERS[name]()
    return module.measure(observations)
