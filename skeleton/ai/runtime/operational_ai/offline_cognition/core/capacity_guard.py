"""Fail-closed finite capacity projections for one approved offline model scope.

These are resource preflight and in-process accounting primitives. They are
not the canonical cross-process SQLite work-order ledger and may never be used
to retry native effects or certify installation/device readiness.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from .contracts import Scope, identifier, integer, sha, refuse
from .receipts import NativeReceipt
from .scheduler import FairQueue, Task

MAX_REQUESTS=512
MAX_RESERVATIONS=4096

@dataclass(frozen=True, slots=True)
class CapacitySnapshot:
    scope: Scope
    epoch: int
    sampled_ns: int
    expires_ns: int
    memory_free_bytes: int
    disk_free_bytes: int
    tokens_left: int
    slots_free: int
    wall_ms_left: int
    observer_attested: bool

    def __post_init__(self):
        if type(self.scope) is not Scope:
            refuse("exact model+tenant+subject snapshot scope required")
        integer(self.epoch,minimum=1)
        integer(self.sampled_ns)
        integer(self.expires_ns,minimum=self.sampled_ns+1)
        if self.expires_ns-self.sampled_ns>60_000_000_000:
            refuse("capacity telemetry must expire within 60 seconds")
        integer(self.memory_free_bytes,maximum=2**40)
        integer(self.disk_free_bytes,maximum=2**40)
        integer(self.tokens_left,maximum=262144)
        integer(self.slots_free,maximum=100000)
        integer(self.wall_ms_left,maximum=3_600_000)
        if type(self.observer_attested) is not bool:
            refuse("capacity observer assertion must be explicit")

@dataclass(frozen=True, slots=True)
class ResourceRequest:
    scope: Scope
    request_id: str
    source_sha256: str
    tokens: int
    memory_bytes: int
    disk_bytes: int
    slots: int
    wall_ms: int
    deadline_ns: int

    def __post_init__(self):
        if type(self.scope) is not Scope:
            refuse("resource request must carry canonical owner identity")
        identifier(self.request_id)
        sha(self.source_sha256)
        integer(self.tokens,minimum=1,maximum=262144)
        integer(self.memory_bytes,minimum=1,maximum=2**40)
        integer(self.disk_bytes,maximum=2**40)
        integer(self.slots,minimum=1,maximum=100000)
        integer(self.wall_ms,minimum=1,maximum=3_600_000)
        integer(self.deadline_ns,minimum=1)

def _active_snapshot(snapshot, now_ns):
    if type(snapshot) is not CapacitySnapshot:
        refuse("typed capacity snapshot required")
    integer(now_ns)
    if not snapshot.sampled_ns<=now_ns<snapshot.expires_ns:
        refuse("stale or future capacity observation")
    if snapshot.observer_attested is not True:
        refuse("untrusted hardware observation cannot admit work")
    return snapshot

def preview(snapshot, requests, *, now_ns):
    """All-or-reject scope check; bounded deterministic multi-dimensional plan."""
    _active_snapshot(snapshot,now_ns)
    if type(requests) not in (tuple,list) or not 1<=len(requests)<=MAX_REQUESTS:
        refuse("finite admission batch required")
    if any(type(r) is not ResourceRequest or r.scope!=snapshot.scope for r in requests):
        refuse("cross-principal or untyped resource batch")
    if len({r.request_id for r in requests})!=len(requests):
        refuse("duplicate admission request IDs")
    free={"tokens":snapshot.tokens_left,"memory":snapshot.memory_free_bytes,
          "disk":snapshot.disk_free_bytes,"slots":snapshot.slots_free,
          "wall_ms":snapshot.wall_ms_left}
    admitted=[];held=[]
    for r in sorted(requests,key=lambda r:r.request_id):
        demand={"tokens":r.tokens,"memory":r.memory_bytes,"disk":r.disk_bytes,
                "slots":r.slots,"wall_ms":r.wall_ms}
        if r.deadline_ns<=now_ns or r.deadline_ns-now_ns<r.wall_ms*1_000_000:
            held.append((r.request_id,"deadline"))
        elif any(demand[k]>free[k] for k in demand):
            held.append((r.request_id,"capacity"))
        else:
            admitted.append(r.request_id)
            for k in demand:
                free[k]-=demand[k]
    return {"admitted":tuple(admitted),"held":tuple(held),
            "remaining":dict(free),"scope_sha256":snapshot.scope.digest(),
            "epoch":snapshot.epoch,"observer_signature_verified_here":False,
            "durable_reservation_made":False,"native_execution_authorized":False}

def pressure_gate(snapshot, *, now_ns, memory_guard_bytes, disk_guard_bytes):
    """Observational gate; no inference permission is minted by hardware facts."""
    _active_snapshot(snapshot,now_ns)
    integer(memory_guard_bytes,minimum=1,maximum=2**40)
    integer(disk_guard_bytes,minimum=1,maximum=2**40)
    reasons=[]
    if snapshot.memory_free_bytes<memory_guard_bytes:
        reasons.append("memory-pressure")
    if snapshot.disk_free_bytes<disk_guard_bytes:
        reasons.append("disk-pressure")
    if snapshot.slots_free<=0:
        reasons.append("concurrency-saturated")
    if snapshot.tokens_left<=0:
        reasons.append("tokens-exhausted")
    return {"held":bool(reasons),"reasons":tuple(reasons),
            "observer_attestation_validated_externally":False,
            "model_device_qualified":False}

class QuotaProjection:
    """In-process token reservation CAS; not a durable model/ledger authority."""

    def __init__(self, scope, *, epoch, token_ceiling, max_pending=MAX_RESERVATIONS):
        if type(scope) is not Scope:
            refuse("operator model scope required")
        integer(epoch,minimum=1)
        integer(token_ceiling,minimum=1,maximum=262144)
        integer(max_pending,minimum=1,maximum=MAX_RESERVATIONS)
        self.scope=scope
        self.epoch=epoch
        self.ceiling=token_ceiling
        self.max_pending=max_pending
        self.spent=0
        self.pending={}
        self.done={}
        self.revision=1
        self.lock=RLock()

    def status(self):
        with self.lock:
            held=sum(v["request"].tokens for v in self.pending.values())
            return {"epoch":self.epoch,"revision":self.revision,
                    "remaining_tokens":self.ceiling-self.spent-held,
                    "reserved_tokens":held,"spent_tokens":self.spent,
                    "pending":len(self.pending),"committed":len(self.done),
                    "durable_across_restart":False,
                    "native_execution_authorized":False}

    def reserve(self, request, *, expected_revision, now_ns):
        if type(request) is not ResourceRequest or request.scope!=self.scope:
            refuse("resource principal/model mismatch")
        integer(expected_revision,minimum=1)
        integer(now_ns)
        if request.deadline_ns<=now_ns:
            refuse("expired resource request")
        with self.lock:
            if expected_revision!=self.revision:
                refuse("stale quota revision")
            if request.request_id in self.pending or request.request_id in self.done:
                refuse("duplicate quota request")
            if len(self.pending)>=self.max_pending:
                refuse("bounded outstanding capacity exceeded")
            if request.tokens>self.status()["remaining_tokens"]:
                refuse("token window exhausted")
            self.pending[request.request_id]={"request":request,"dispatched":False}
            self.revision+=1
            return {"request_id":request.request_id,"revision":self.revision,
                    "native_execution_permitted":False,
                    "durable_lease":False}

    def mark_dispatch_unknown(self, request_id, *, expected_revision):
        identifier(request_id)
        integer(expected_revision,minimum=1)
        with self.lock:
            if self.revision!=expected_revision or request_id not in self.pending:
                refuse("stale or missing native dispatch fence")
            self.pending[request_id]["dispatched"]=True
            self.revision+=1
            return {"state":"native-effect-unknown-held",
                    "revision":self.revision,"automatic_retry":False,
                    "durable_dispatch_fence_written":False}

    def cancel_before_dispatch(self, request_id, *, expected_revision):
        identifier(request_id)
        integer(expected_revision,minimum=1)
        with self.lock:
            if self.revision!=expected_revision or request_id not in self.pending:
                refuse("stale/missing pre-dispatch cancellation")
            if self.pending[request_id]["dispatched"]:
                refuse("unknown native effect cannot be refunded")
            del self.pending[request_id]
            self.revision+=1
            return {"state":"cancelled-before-dispatch",
                    "revision":self.revision,"unconsumed_reservation_released":True,
                    "native_execution_performed":False}

    def settle_committed(self, receipt, *, expected_revision):
        if type(receipt) is not NativeReceipt or receipt.scope!=self.scope:
            refuse("canonical model/tenant/subject receipt required")
        integer(expected_revision,minimum=1)
        with self.lock:
            if expected_revision!=self.revision:
                refuse("stale settlement revision")
            old=self.done.get(receipt.request_id)
            if old is not None:
                if old["output_sha256"]!=receipt.output_sha256 or (
                    old["input_tokens"],old["output_tokens"]
                )!=(receipt.input_tokens,receipt.output_tokens):
                    refuse("conflicting committed model output")
                return {"state":"already-settled","revision":self.revision,
                        "double_charged":False}
            entry=self.pending.get(receipt.request_id)
            if entry is None:
                refuse("no reserved request to charge")
            requested=entry["request"]
            if receipt.input_tokens+receipt.output_tokens>requested.tokens:
                refuse("actual native tokens exceed reserved ceiling")
            if not entry["dispatched"] or receipt.replayed:
                refuse("first settlement needs a committed non-replayed native result")
            charge=receipt.input_tokens+receipt.output_tokens
            self.spent+=charge
            self.done[receipt.request_id]={
                "output_sha256":receipt.output_sha256,
                "input_tokens":receipt.input_tokens,
                "output_tokens":receipt.output_tokens,
            }
            del self.pending[receipt.request_id]
            self.revision+=1
            return {"state":"settled-committed","revision":self.revision,
                    "tokens_charged":charge,"double_charged":False,
                    "durable_source_receipt_independently_verified":False}

def fair_preview(tasks, weights, *, now_ns, token_capacity):
    """In-memory weighted fair queue demonstration; never a durable dispatch."""
    integer(now_ns);integer(token_capacity,minimum=1,maximum=262144)
    if type(tasks) not in (tuple,list) or not 1<=len(tasks)<=MAX_REQUESTS:
        refuse("bounded task batch required")
    if type(weights) is not dict:
        refuse("explicit per-tenant weights required")
    if len({t.job_id for t in tasks})!=len(tasks):
        refuse("duplicate task identity")
    queue=FairQueue(maximum=MAX_REQUESTS)
    for task in tasks:
        if type(task) is not Task or task.tenant not in weights:
            refuse("unknown tenant or untyped task")
        queue.enqueue(task,weight=weights[task.tenant])
    result=queue.admit(now_ns=now_ns,capacity_tokens=token_capacity)
    return {**result,"durable_queue":False,"native_worker_dispatched":False}

def preemption_hold(request, *, dispatched, operator_approved):
    """A preemption request cannot cancel already dispatched native work."""
    if type(request) is not ResourceRequest:
        refuse("typed existing request required")
    if type(dispatched) is not bool or type(operator_approved) is not bool:
        refuse("explicit dispatch and operator input required")
    if dispatched:
        return {"state":"native-effect-unknown-held","automatic_refund":False,
                "requires_canonical_spine_reconciliation":True}
    if not operator_approved:
        return {"state":"operator-approval-held","automatic_refund":False,
                "requires_canonical_spine_reconciliation":False}
    return {"state":"pre-dispatch-cancel-requested","automatic_refund":False,
            "requires_canonical_spine_reconciliation":False}
