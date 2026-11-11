"""Approved deployment measurements and strict local lookup."""
ALLOWED=frozenset(('install_complete_fraction', 'missing_shard_fraction', 'verified_bytes_ratio', 'daemon_uptime', 'restart_success_ratio', 'memory_pressure_ratio', 'startup_held_ratio', 'manifest_completeness', 'health_probe_success_ratio', 'canary_pass_rate', 'device_coverage', 'native_e2e_coverage'))
def measure(name,observations):
    if type(name) is not str or name not in ALLOWED:
        raise ValueError('unknown measurement contract')
    if name == "install_complete_fraction":
        from . import install_complete_fraction as module
    elif name == "missing_shard_fraction":
        from . import missing_shard_fraction as module
    elif name == "verified_bytes_ratio":
        from . import verified_bytes_ratio as module
    elif name == "daemon_uptime":
        from . import daemon_uptime as module
    elif name == "restart_success_ratio":
        from . import restart_success_ratio as module
    elif name == "memory_pressure_ratio":
        from . import memory_pressure_ratio as module
    elif name == "startup_held_ratio":
        from . import startup_held_ratio as module
    elif name == "manifest_completeness":
        from . import manifest_completeness as module
    elif name == "health_probe_success_ratio":
        from . import health_probe_success_ratio as module
    elif name == "canary_pass_rate":
        from . import canary_pass_rate as module
    elif name == "device_coverage":
        from . import device_coverage as module
    elif name == "native_e2e_coverage":
        from . import native_e2e_coverage as module
    else:
        raise ValueError('unknown measurement contract')
    return module.measure(observations)
