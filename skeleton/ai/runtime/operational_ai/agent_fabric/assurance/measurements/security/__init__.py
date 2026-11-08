"""Approved security measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('signed_grant_fraction', 'deny_rate', 'tools_by_scope', 'replay_rejection_fraction', 'lease_expiry_margin', 'unauthorized_attempt_ratio', 'checksum_failure_rate', 'permission_scope_density', 'approval_age', 'leakage_prevention_rate', 'revoked_source_fraction', 'path_guard_rejections'))
_LOADERS = {
    "signed_grant_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.signed_grant_fraction"),
    "deny_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.deny_rate"),
    "tools_by_scope": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.tools_by_scope"),
    "replay_rejection_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.replay_rejection_fraction"),
    "lease_expiry_margin": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.lease_expiry_margin"),
    "unauthorized_attempt_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.unauthorized_attempt_ratio"),
    "checksum_failure_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.checksum_failure_rate"),
    "permission_scope_density": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.permission_scope_density"),
    "approval_age": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.approval_age"),
    "leakage_prevention_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.leakage_prevention_rate"),
    "revoked_source_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.revoked_source_fraction"),
    "path_guard_rejections": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security.path_guard_rejections"),
}

def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=_LOADERS[name]()
    return module.measure(observations)
