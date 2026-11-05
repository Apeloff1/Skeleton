"""Time to authority expiry at observation.

Independent, bounded measurement only: never grants release status or model authority.
"""
from __future__ import annotations
import math
from skeleton.ai.runtime.operational_ai.agent_fabric.core.canonical import canonical
from skeleton.ai.runtime.operational_ai.agent_fabric.core.errors import Invalid
FIELDS=('expires_ns', 'observed_ns')
NAME='lease_expiry_margin'
DOMAIN='security'

def measure(observations:dict[str,float])->dict:
    """Compute time to authority expiry at observation from exactly the named input counters."""
    if not isinstance(observations,dict) or set(observations)!=set(FIELDS):
        raise Invalid('measurement requires exact approved counters')
    for key in FIELDS:
        value=observations[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=10**18:
            raise Invalid('counter must be finite, nonnegative, and bounded')
    expires_ns, observed_ns=(float(observations[key]) for key in FIELDS)
    score=max(0,(expires_ns-observed_ns)/1000000)
    if not math.isfinite(score) or abs(score)>10**35:
        raise Invalid('measurement exceeds finite result bound')
    raw=canonical(observations,ceiling=4096)
    from hashlib import sha256
    return {'schema':'agent.measurement.v1','domain':DOMAIN,'metric':NAME,
            'value':score,'inputs_sha256':sha256(raw).hexdigest(),
            'assessment':'observed-only-not-model-or-release-certification'}
