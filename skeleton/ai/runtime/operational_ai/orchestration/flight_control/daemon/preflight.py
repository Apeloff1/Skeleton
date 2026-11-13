"""Prove owner/worker binding and durable queue integrity before serving."""
from __future__ import annotations
from .. import doctor,watchdog,controls
from .contracts import DaemonHeld,DaemonPolicy

def inspect(application,policy:DaemonPolicy)->dict:
    if (application.worker.ledger is not application.ledger or
        application.worker.spine is not application.spine or
        application.ledger.db is not application.spine.db or
        application.ledger.identity!=application.spine.identity):
        raise DaemonHeld('live worker and database do not share identity')
    if application.spine.backend is None:
        raise DaemonHeld('native model backend missing')
    if (getattr(application.spine.backend,'model_digest',None)!=application.spine.identity.model_sha256 or
        getattr(application.spine.backend,'tokenizer_digest',None)!=application.spine.identity.tokenizer_sha256):
        raise DaemonHeld('backend digest differs from owned model')
    application.spine.db.inspect()
    proof=doctor.inspect(application.ledger,max_jobs=policy.startup_max_jobs,
                         max_events_per_job=policy.startup_max_events_per_job)
    watch=watchdog.report(application.ledger,limit=policy.startup_max_jobs)
    if watch['stale_count']:
        raise DaemonHeld('stale inference detected; independent operator recovery required')
    stamp=application.ledger.clock.stamp()
    if not stamp.boot or stamp.tick<=0:
        raise DaemonHeld('kernel boot fencing not available')
    return {'state':proof['mode'],'reviewed_jobs':proof['jobs'],
            'verified_events':proof['events'],'stale_jobs':watch['stale_count'],
            'identity':application.spine.identity.key(),
            'contract':'startup-inventory-only-no-real-model-canary'}
