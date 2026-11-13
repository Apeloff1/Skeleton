"""Machine-readable critical path proof; skipped checks are never success."""
from __future__ import annotations
from .contracts import SpineError
CHECKS=(
 'canonical-ai-tree','build-order','local-unit','native-model-e2e',
 'first-install','model-license','device-memory','device-latency',
 'merge-readiness','backend-quality','app-e2e','workflow-input-security',
 'sealed-context-guard','artifact-policy','malware-gate',
 'repository-hygiene','secret-scanning','dependency-review',
)
STATUS={'pass','fail','pending','skipped','cancelled','unknown'}

def evaluate(values:dict[str,str])->dict:
    if not isinstance(values,dict) or not set(values).issubset(CHECKS):
        raise SpineError('unrecognized readiness check')
    statuses={name:values.get(name,'unknown') for name in CHECKS}
    if any(v not in STATUS for v in statuses.values()):raise SpineError('invalid check outcome')
    blocked=[name for name,outcome in statuses.items() if outcome!='pass']
    # Caller-supplied check strings are not verifiable CI evidence. Even an
    # all-pass claim is insufficient to authorize a production release.
    return {'release_accepted':False,'all_claimed_checks_passed':not blocked,
        'unqualified_checks':blocked,
        'status':'unverified-claims-not-release-authority' if not blocked else 'release-held',
        'checked':statuses}
