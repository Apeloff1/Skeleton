"""Approved deployment measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('install_complete_fraction', 'missing_shard_fraction', 'verified_bytes_ratio', 'daemon_uptime', 'restart_success_ratio', 'memory_pressure_ratio', 'startup_held_ratio', 'manifest_completeness', 'health_probe_success_ratio', 'canary_pass_rate', 'device_coverage', 'native_e2e_coverage'))
def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=import_module('skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment.'+name)
    return module.measure(observations)
