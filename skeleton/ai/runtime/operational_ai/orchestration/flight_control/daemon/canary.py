"""Live-model-only admission canary, no fixture or replay masquerading as a pass.

Uses the actual activated GGUF backend and durable queue. This is an operator
qualifier, not a production request path, and should run in a disposable private
state directory so it cannot alter ordinary user conversations.
"""
from __future__ import annotations
from secrets import token_hex
from .contracts import DaemonHeld
from .. import doctor
from ..contracts import FlightSpec

def run_live_canary(application,*,challenge:str='Answer one sentence in plain English.') -> dict:
    if not isinstance(challenge,str) or not challenge.strip() or len(challenge.encode('utf8'))>1024:
        raise DaemonHeld('bounded original canary challenge required')
    session='canary_'+token_hex(12)
    request='challenge_'+token_hex(12)
    job='canaryjob_'+token_hex(12)
    spine=application.spine
    ledger=application.ledger
    if (application.worker.ledger is not ledger or application.worker.spine is not spine or
        spine.identity!=ledger.identity):
        raise DaemonHeld('canary requires one live authority')
    from ....model.gguf.runtime import GGUFBackend
    if not isinstance(spine.backend,GGUFBackend):
        raise DaemonHeld('real GGUF native backend is required for canary')
    if doctor.inspect(ledger)['jobs']!=0:
        raise DaemonHeld('native canary must use a fresh, isolated state')
    spine.create(session)
    submit=ledger.submit(FlightSpec(spine.identity,job,session,request,challenge))
    if submit['state']!='queued':raise DaemonHeld('live canary admission must be newly queued')
    outcome=application.worker.run_one()
    if outcome is None or outcome.job_id!=job or outcome.state!='completed' or outcome.recovered:
        raise DaemonHeld('canary must execute exactly one new native inference')
    persisted=spine.replay(session,request,challenge)
    if persisted is None or persisted['revision']!=1:
        raise DaemonHeld('native canary missing authoritative receipt')
    result=ledger.inspect(job)
    if result['state']!='completed' or result['result']['output_sha256']!=persisted['output_sha256']:
        raise DaemonHeld('canary durable receipt mismatch')
    audit=doctor.inspect(ledger)
    return {'status':'native-canary-transaction-verified','model_sha256':spine.identity.model_sha256,
            'tokenizer_sha256':spine.identity.tokenizer_sha256,
            'request_sha256':persisted['request_sha256'],
            'output_sha256':persisted['output_sha256'],
            'job_state':result['state'],'revision':persisted['revision'],
            'queue_events_verified':audit['events'], 'real_model_activation':'caller-proved',
            'claims_excluded':['quality','device-qualification','release','model-licensing']}
