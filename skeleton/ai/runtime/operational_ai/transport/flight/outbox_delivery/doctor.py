"""No-mutation preflight tying exact principal state to local event spool."""
from __future__ import annotations
from .audit import verify_custody
from .contracts import DeliveryHeld

def inspect(ledger,sink,*,limit:int=4096)->dict:
    report=verify_custody(ledger,sink,limit=limit)
    with ledger.db.snapshot() as conn:
        # SQLite's global chain checker is read-only; it is not a proof that
        # the untrusted model output is true or that release gates succeeded.
        from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.chain import verify
        chain=verify(conn,limit=100000)
    return {'schema':'skeleton.ai.private-spool-doctor.v1',
            'custody':report,'spine_audit_head':chain['head'],
            'spine_audit_entries':chain['entries'],
            'release_accepted':False,'model_calls':0}
