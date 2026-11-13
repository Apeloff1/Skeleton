"""Content-addressed custody violations.

Independent, bounded measurement only: never grants release status or model authority.
"""
from __future__ import annotations
import math
from skeleton.ai.runtime.operational_ai.agent_fabric.core.canonical import canonical
from skeleton.ai.runtime.operational_ai.agent_fabric.core.errors import Invalid
FIELDS=('digest_mismatches', 'checked_artifacts')
NAME='checksum_failure_rate'
DOMAIN='security'

def measure(observations:dict[str,float])->dict:
    """Compute content-addressed custody violations from exactly the named input counters."""
    if not isinstance(observations,dict) or set(observations)!=set(FIELDS):
        raise Invalid('measurement requires exact approved counters')
    for key in FIELDS:
        value=observations[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=10**18:
            raise Invalid('counter must be finite, nonnegative, and bounded')
    digest_mismatches, checked_artifacts=(float(observations[key]) for key in FIELDS)
    score=digest_mismatches/max(checked_artifacts,1)
    if not math.isfinite(score) or abs(score)>10**35:
        raise Invalid('measurement exceeds finite result bound')
    raw=canonical(observations,ceiling=4096)
    from hashlib import sha256
    return {'schema':'agent.measurement.v1','domain':DOMAIN,'metric':NAME,
            'value':score,'inputs_sha256':sha256(raw).hexdigest(),
            'assessment':'observed-only-not-model-or-release-certification'}
