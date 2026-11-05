"""All-or-none bounded batch admission, with exact idempotent submissions."""
from __future__ import annotations
from .contracts import FlightSpec,FlightConflict,FlightBusy


def submit_many(ledger,specs,*,maximum:int=128)->tuple[dict,...]:
    if type(maximum)is not int or not 1<=maximum<=256:
        raise FlightConflict('invalid batch upper bound')
    # Materialize only up to maximum+1, preventing unbounded generators.
    from itertools import islice
    entries=tuple(islice(iter(specs),maximum+1))
    if not entries or len(entries)>maximum:
        raise FlightConflict('submission batch empty or exceeds finite limit')
    if any(not isinstance(x,FlightSpec) for x in entries):
        raise FlightConflict('batch contains invalid inference contract')
    identities={(x.job_id,x.session,x.request_id) for x in entries}
    if len(identities)!=len(entries) or len({x.job_id for x in entries})!=len(entries) or len({(x.session,x.request_id) for x in entries})!=len(entries):
        raise FlightConflict('duplicate durable job or request key in batch')
    if any(x.identity!=ledger.identity for x in entries):
        raise FlightConflict('cross-principal batch is prohibited')
    stamp=ledger.clock.stamp()
    with ledger.db.transaction() as conn:
        return tuple(ledger._submit_locked(conn,x,stamp) for x in entries)
