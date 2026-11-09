"""Approved security measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('signed_grant_fraction', 'deny_rate', 'tools_by_scope', 'replay_rejection_fraction', 'lease_expiry_margin', 'unauthorized_attempt_ratio', 'checksum_failure_rate', 'permission_scope_density', 'approval_age', 'leakage_prevention_rate', 'revoked_source_fraction', 'path_guard_rejections'))
def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=import_module('skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.'+name)
    return module.measure(observations)
