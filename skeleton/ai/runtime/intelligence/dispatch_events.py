"""Bounded event coordination proposals for the existing dispatcher owners.

These functions do not drop events, execute handlers, publish timers or allocate
singleton ownership. The host must authenticate event receipts and atomically
claim the returned identities in its canonical durable owner before execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from collections import defaultdict

from .dispatch_policy import DispatchPolicyError, bounded_int, identifier
from .dispatch_cognitive import digest, binding

MAX_EVENTS = 4096


@dataclass(frozen=True, slots=True)
class EventRecord:
    event_id: str
    tenant_id: str
    stream_id: str
    key: str
    policy_sha256: str
    payload_sha256: str
    arrival_ms: int
    payload_bytes: int

    def __post_init__(self) -> None:
        for v in (self.event_id,self.tenant_id,self.stream_id,self.key):
            identifier(v)
        digest(self.policy_sha256)
        digest(self.payload_sha256)
        bounded_int(self.arrival_ms,"arrival")
        bounded_int(self.payload_bytes,"payload bytes",1)

    @property
    def scope(self) -> tuple[str,str,str,str]:
        return self.tenant_id,self.stream_id,self.key,self.policy_sha256


@dataclass(frozen=True, slots=True)
class WindowPolicy:
    quiet_ms: int
    maximum_wait_ms: int
    maximum_items: int
    maximum_bytes: int

    def __post_init__(self) -> None:
        bounded_int(self.quiet_ms,"quiet interval",1,3600000)
        bounded_int(self.maximum_wait_ms,"maximum wait",self.quiet_ms,86400000)
        bounded_int(self.maximum_items,"event ceiling",1,1024)
        bounded_int(self.maximum_bytes,"byte ceiling",1,64*1024**2)


@dataclass(frozen=True, slots=True)
class EventWindow:
    scope: tuple[str,str,str,str]
    event_ids: tuple[str,...]
    ready_ms: int
    ready: bool
    payload_bytes: int
    window_sha256: str


def coalesce_events(records: Sequence[EventRecord], policy: WindowPolicy, *, now_ms: int) -> tuple[EventWindow,...]:
    """Group quiet-window events without dropping or replacing payload identities.

    The first arrival bounds max wait even under continual arrivals. Each
    window closes at size/bytes/cutoff; another tenant/key/policy never joins.
    Exact replays deduplicate only byte-identical records with identical scope.
    No event is invisible due to an oversized payload: reject the whole input.
    """
    bounded_int(now_ms,"now")
    if not isinstance(policy,WindowPolicy) or len(records)>MAX_EVENTS:
        raise DispatchPolicyError("invalid event window input")
    identities: dict[tuple[str,str],EventRecord]={}
    for row in records:
        if not isinstance(row,EventRecord) or row.arrival_ms>now_ms or row.payload_bytes>policy.maximum_bytes:
            raise DispatchPolicyError("invalid or oversized event")
        key=(row.tenant_id,row.event_id)
        if key in identities and identities[key]!=row:
            raise DispatchPolicyError("event replay identity conflict")
        identities[key]=row
    scopes: dict[tuple,list[EventRecord]]=defaultdict(list)
    for row in identities.values():
        scopes[row.scope].append(row)
    result=[]
    for scope in sorted(scopes):
        rows=sorted(scopes[scope],key=lambda r:(r.arrival_ms,r.event_id))
        pending=[]
        size=0
        cutoff=0
        def emit(ready_ms: int) -> None:
            event_ids=tuple(r.event_id for r in pending)
            result.append(EventWindow(scope,event_ids,ready_ms,now_ms>=ready_ms,size,
                binding("event-window-v1",scope,policy.quiet_ms,policy.maximum_wait_ms,
                        policy.maximum_items,policy.maximum_bytes,ready_ms,
                        [(r.event_id,r.payload_sha256,r.arrival_ms,r.payload_bytes) for r in pending])))
        for row in rows:
            if pending and (row.arrival_ms>=cutoff or len(pending)>=policy.maximum_items
                            or size+row.payload_bytes>policy.maximum_bytes):
                emit(min(cutoff,row.arrival_ms))
                pending=[]
                size=0
            pending.append(row)
            size+=row.payload_bytes
            cutoff=min(pending[0].arrival_ms+policy.maximum_wait_ms,row.arrival_ms+policy.quiet_ms)
            if len(pending)==policy.maximum_items or size==policy.maximum_bytes:
                emit(row.arrival_ms)
                pending=[]
                size=0
        if pending:
            emit(cutoff)
    return tuple(sorted(result,key=lambda w:(w.ready_ms,w.scope,w.event_ids)))


@dataclass(frozen=True, slots=True)
class SingletonObservation:
    tenant_id: str
    key: str
    policy_sha256: str
    owner_task_id: str
    generation: int
    phase: str

    def __post_init__(self) -> None:
        for v in (self.tenant_id,self.key,self.owner_task_id):
            identifier(v)
        digest(self.policy_sha256)
        bounded_int(self.generation,"generation")
        if self.phase not in {"active","uncertain","released"}:
            raise DispatchPolicyError("invalid singleton phase")


def singleton_eligible(window: EventWindow, observations: Sequence[SingletonObservation], *, generation: int) -> bool:
    """A ready window may propose acquisition only without live/unknown ownership."""
    if not isinstance(window,EventWindow) or len(observations)>MAX_EVENTS:
        raise DispatchPolicyError("invalid singleton observation")
    bounded_int(generation,"generation")
    if any(not isinstance(o,SingletonObservation) or o.generation!=generation for o in observations):
        raise DispatchPolicyError("mixed singleton observation generations")
    tenant,stream,key,policy=window.scope
    # Stream IDs may differ but the configured keyed exclusivity spans streams.
    matching=[o for o in observations if (o.tenant_id,o.key,o.policy_sha256)==(tenant,key,policy)]
    if len({o.owner_task_id for o in matching})!=len(matching):
        raise DispatchPolicyError("duplicate singleton owner")
    return window.ready and not any(o.phase in {"active","uncertain"} for o in matching)


@dataclass(frozen=True, slots=True)
class WaitIntent:
    task_id: str
    tenant_id: str
    stream_id: str
    key: str
    policy_sha256: str
    generation: int
    registered_ms: int
    timeout_ms: int

    def __post_init__(self) -> None:
        for v in (self.task_id,self.tenant_id,self.stream_id,self.key):
            identifier(v)
        digest(self.policy_sha256)
        bounded_int(self.generation,"generation")
        bounded_int(self.registered_ms,"registration")
        bounded_int(self.timeout_ms,"timeout",self.registered_ms+1)


@dataclass(frozen=True, slots=True)
class WakeProposal:
    task_id: str
    disposition: str
    event_id: str | None
    evidence_sha256: str


def correlate_waits(waits: Sequence[WaitIntent], records: Sequence[EventRecord], *,
                    generation: int, now_ms: int) -> tuple[WakeProposal,...]:
    """Plan a wake upon the earliest eligible receipt or a verified time boundary.

    One event may satisfy multiple independently registered wait intents.
    Exact generation and input scope are bound; actual wake must be committed
    atomically with the owner's durable wait state. This is not a timer service.
    """
    bounded_int(generation,"generation")
    bounded_int(now_ms,"now")
    if len(waits)>MAX_EVENTS or len(records)>MAX_EVENTS:
        raise DispatchPolicyError("wait correlation ceiling")
    index: dict[tuple,list[EventRecord]]=defaultdict(list)
    seen={}
    for r in records:
        if not isinstance(r,EventRecord) or r.arrival_ms>now_ms:
            raise DispatchPolicyError("invalid event receipt")
        identity=(r.tenant_id,r.event_id)
        if identity in seen:
            if seen[identity]!=r:
                raise DispatchPolicyError("event identity conflict")
            continue
        seen[identity]=r
        index[r.scope].append(r)
    for rows in index.values():
        rows.sort(key=lambda r:(r.arrival_ms,r.event_id))
    if any(not isinstance(w,WaitIntent) or w.generation!=generation or w.registered_ms>now_ms for w in waits):
        raise DispatchPolicyError("invalid wait generation")
    if len({(w.tenant_id,w.task_id) for w in waits})!=len(waits):
        raise DispatchPolicyError("duplicate wait intent")
    from bisect import bisect_left
    timeline={key:[r.arrival_ms for r in rows] for key,rows in index.items()}
    result=[]
    for w in sorted(waits,key=lambda w:(w.tenant_id,w.task_id)):
        scope=(w.tenant_id,w.stream_id,w.key,w.policy_sha256)
        rows=index.get(scope,[])
        i=bisect_left(timeline.get(scope,[]),w.registered_ms)
        r=rows[i] if i<len(rows) and rows[i].arrival_ms<w.timeout_ms else None
        state="event" if r else "timeout" if now_ms>=w.timeout_ms else "waiting"
        result.append(WakeProposal(w.task_id,state,r.event_id if r else None,
            binding("wake-v1",scope,w.task_id,w.generation,w.registered_ms,w.timeout_ms,state,
                    (r.event_id,r.payload_sha256,r.arrival_ms) if r else None)))
    return tuple(result)
