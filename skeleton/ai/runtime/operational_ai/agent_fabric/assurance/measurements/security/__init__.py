"""Approved security measurements and strict local lookup."""
ALLOWED=frozenset(('signed_grant_fraction', 'deny_rate', 'tools_by_scope', 'replay_rejection_fraction', 'lease_expiry_margin', 'unauthorized_attempt_ratio', 'checksum_failure_rate', 'permission_scope_density', 'approval_age', 'leakage_prevention_rate', 'revoked_source_fraction', 'path_guard_rejections'))
def measure(name,observations):
    if type(name) is not str or name not in ALLOWED:
        raise ValueError('unknown measurement contract')
    if name == "signed_grant_fraction":
        from . import signed_grant_fraction as module
    elif name == "deny_rate":
        from . import deny_rate as module
    elif name == "tools_by_scope":
        from . import tools_by_scope as module
    elif name == "replay_rejection_fraction":
        from . import replay_rejection_fraction as module
    elif name == "lease_expiry_margin":
        from . import lease_expiry_margin as module
    elif name == "unauthorized_attempt_ratio":
        from . import unauthorized_attempt_ratio as module
    elif name == "checksum_failure_rate":
        from . import checksum_failure_rate as module
    elif name == "permission_scope_density":
        from . import permission_scope_density as module
    elif name == "approval_age":
        from . import approval_age as module
    elif name == "leakage_prevention_rate":
        from . import leakage_prevention_rate as module
    elif name == "revoked_source_fraction":
        from . import revoked_source_fraction as module
    elif name == "path_guard_rejections":
        from . import path_guard_rejections as module
    else:
        raise ValueError('unknown measurement contract')
    return module.measure(observations)
