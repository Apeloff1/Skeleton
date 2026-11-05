"""Read-only journal event paging; not falsely advertised as live token stream."""
from __future__ import annotations
from ..authority.canonical import ContractViolation
from ..persistence.journal import EventJournal


def page(journal:EventJournal,stream:str,*,after:int=0,limit:int=64)->dict:
    if type(after) is not int or after<0 or type(limit) is not int or not 1<=limit<=256:
        raise ContractViolation("invalid audit replay page bounds")
    events=journal.replay(stream)
    selected=events[after:after+limit]
    if after>len(events):
        raise ContractViolation("audit cursor exceeds retained journal")
    return {"stream":stream,"after":after,
            "events":[{"sequence":e.seq,"kind":e.kind,"event_id":e.event_id,
                       "sha256":e.digest,"previous_sha256":e.previous_digest,
                       "payload":e.payload} for e in selected],
            "next_after":after+len(selected) if after+len(selected)<len(events) else None,
            "replay_kind":"committed-audit-events-not-live-generation"}
