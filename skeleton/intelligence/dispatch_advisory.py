"""Bounded dispatch research kernels; proposals, not worker or tool authority.

All observations must be supplied by existing trusted owners. No queue,
credentials, physical device allocation, or side effect is owned here.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction
from collections.abc import Sequence
from typing import Literal

from .dispatch_policy import (
    DispatchPolicyError, bounded_int, identifier, MAX_CANDIDATES,
)


@dataclass(frozen=True, slots=True)
class RouteDemand:
    tenant: str
    model_sha256: str
    tokenizer_sha256: str
    required: frozenset[str]
    prompt_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        identifier(self.tenant)
        _sha(self.model_sha256)
        _sha(self.tokenizer_sha256)
        _labels(self.required)
        bounded_int(self.prompt_tokens, "prompt tokens", 1)
        bounded_int(self.output_tokens, "output tokens", 1)


def _sha(value: str) -> None:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise DispatchPolicyError("invalid digest")


def _labels(values: frozenset[str]) -> None:
    if type(values) is not frozenset or len(values) > 256:
        raise DispatchPolicyError("invalid capabilities")
    for value in values:
        identifier(value)


@dataclass(frozen=True, slots=True)
class RouteWorker:
    worker: str
    tenant: str
    model_sha256: str
    tokenizer_sha256: str
    capabilities: frozenset[str]
    free_tokens: int
    queued_tokens: int
    resident_prefix_tokens: int
    observed_ms: int
    generation: int
    healthy: bool

    def __post_init__(self) -> None:
        identifier(self.worker)
        identifier(self.tenant)
        _sha(self.model_sha256)
        _sha(self.tokenizer_sha256)
        _labels(self.capabilities)
        for value in (self.free_tokens, self.queued_tokens, self.resident_prefix_tokens, self.observed_ms, self.generation):
            bounded_int(value, "worker observation")
        if type(self.healthy) is not bool:
            raise DispatchPolicyError("invalid worker health")


@dataclass(frozen=True, slots=True)
class RouteProposal:
    worker: str
    generation: int
    reserved_tokens: int
    reason: str
    observation_ms: int


def choose_route(
    demand: RouteDemand, workers: Sequence[RouteWorker], *, now_ms: int,
    max_age_ms: int = 5_000, imbalance_tokens: int = 512,
    imbalance_ratio: int = 2,
) -> RouteProposal | None:
    """Use exact identity, eligibility, fresh capacity and bounded cache affinity.

    A cache hint never reduces the admission budget. It affects preference
    only; the physical owner still verifies actual prefix custody.
    """
    bounded_int(now_ms, "time")
    bounded_int(max_age_ms, "freshness", 1, 60_000)
    bounded_int(imbalance_tokens, "imbalance", 1)
    bounded_int(imbalance_ratio, "imbalance ratio", 2, 100)
    if not isinstance(demand, RouteDemand) or len(workers) > MAX_CANDIDATES:
        raise DispatchPolicyError("invalid route observation")
    if any(not isinstance(w, RouteWorker) for w in workers):
        raise DispatchPolicyError("invalid worker")
    if len({w.worker for w in workers}) != len(workers):
        raise DispatchPolicyError("duplicate worker")
    reserve = demand.prompt_tokens + demand.output_tokens
    eligible = [
        w for w in workers if w.healthy and w.tenant == demand.tenant
        and w.model_sha256 == demand.model_sha256 and w.tokenizer_sha256 == demand.tokenizer_sha256
        and demand.required <= w.capabilities and w.free_tokens >= reserve
        and 0 <= now_ms - w.observed_ms <= max_age_ms
    ]
    if not eligible:
        return None
    low = min(w.queued_tokens for w in eligible)
    high = max(w.queued_tokens for w in eligible)
    imbalanced = high - low >= imbalance_tokens and high >= max(1, low) * imbalance_ratio
    if imbalanced:
        selected = min(eligible, key=lambda w: (w.queued_tokens, -w.free_tokens, w.worker))
    else:
        selected = min(eligible, key=lambda w: (
            -min(w.resident_prefix_tokens, demand.prompt_tokens), w.queued_tokens,
            -w.free_tokens, w.worker,
        ))
    return RouteProposal(
        selected.worker, selected.generation, reserve,
        "load_balance" if imbalanced else "cache_affinity", selected.observed_ms,
    )


@dataclass(frozen=True, slots=True)
class StealObservation:
    task: str
    donor: str
    recipient: str
    tenant: str
    donor_wait_ms: int
    recipient_wait_ms: int
    execution_ms: int
    transfer_ms: int
    uncertainty_ms: int
    donor_generation: int
    recipient_generation: int
    not_started: bool
    compatible: bool

    def __post_init__(self) -> None:
        for value in (self.task, self.donor, self.recipient, self.tenant):
            identifier(value)
        for value in (self.donor_wait_ms, self.recipient_wait_ms, self.execution_ms,
                      self.transfer_ms, self.uncertainty_ms, self.donor_generation,
                      self.recipient_generation):
            bounded_int(value, "steal observation")
        if self.donor == self.recipient or type(self.not_started) is not bool or type(self.compatible) is not bool:
            raise DispatchPolicyError("invalid steal boundary")


def propose_steal(observations: Sequence[StealObservation], *, minimum_gain_ms: int = 1) -> StealObservation | None:
    """Only propose migration of work not started; require donor revocation before transfer."""
    bounded_int(minimum_gain_ms, "minimum gain", 1)
    if len(observations) > MAX_CANDIDATES or any(not isinstance(o, StealObservation) for o in observations):
        raise DispatchPolicyError("invalid steal observations")
    keys = {(o.tenant, o.task, o.donor, o.recipient) for o in observations}
    if len(keys) != len(observations):
        raise DispatchPolicyError("duplicate steal observation")
    ranked = []
    for o in observations:
        if not o.not_started or not o.compatible or o.execution_ms == 0:
            continue
        gain = o.donor_wait_ms - o.recipient_wait_ms - o.transfer_ms - o.uncertainty_ms
        if gain >= minimum_gain_ms and o.execution_ms >= o.transfer_ms:
            ranked.append((-gain, o.tenant, o.task, o.donor, o.recipient, o))
    return min(ranked, key=lambda row: row[:-1])[-1] if ranked else None


@dataclass(frozen=True, slots=True)
class DurationEstimate:
    samples: int
    median_ms: int
    conservative_ms: int


def estimate_duration(samples_ms: Sequence[int], *, fallback_ms: int, minimum_samples: int = 8) -> DurationEstimate:
    """Order-statistic prediction for pre-scoped, source-compatible completed tasks."""
    bounded_int(fallback_ms, "fallback", 1)
    bounded_int(minimum_samples, "minimum samples", 1, 256)
    if len(samples_ms) > MAX_CANDIDATES:
        raise DispatchPolicyError("sample limit exceeded")
    for value in samples_ms:
        bounded_int(value, "duration sample", 1)
    ordered = sorted(samples_ms)
    n = len(ordered)
    if n < minimum_samples:
        return DurationEstimate(n, fallback_ms, max([fallback_ms, *ordered]))
    return DurationEstimate(n, ordered[(n - 1) // 2], max(fallback_ms, ordered[(95 * n + 99) // 100 - 1]))


RetryKind = Literal["pre-effect-transient", "confirmed-no-effect", "unknown-effect", "permanent", "success"]


@dataclass(frozen=True, slots=True)
class RetryProposal:
    disposition: str
    delay_ms: int


def retry_proposal(
    task: str, *, attempt: int, maximum_attempts: int, remaining_ms: int,
    outcome: RetryKind, base_delay_ms: int = 1000,
    maximum_delay_ms: int = 60_000,
) -> RetryProposal:
    """Unknown external effects never auto-retry; only a proven pre-effect failure can."""
    identifier(task)
    bounded_int(maximum_attempts, "attempt cap", 1, 32)
    bounded_int(attempt, "attempt", 1, maximum_attempts)
    bounded_int(remaining_ms, "remaining time")
    bounded_int(base_delay_ms, "base delay", 1)
    bounded_int(maximum_delay_ms, "delay cap", base_delay_ms)
    if outcome == "unknown-effect":
        return RetryProposal("reconcile", 0)
    if outcome == "permanent":
        return RetryProposal("quarantine", 0)
    if outcome == "success":
        return RetryProposal("complete", 0)
    if outcome not in ("pre-effect-transient", "confirmed-no-effect"):
        raise DispatchPolicyError("unknown outcome")
    if attempt >= maximum_attempts:
        return RetryProposal("exhausted", 0)
    raw = min(maximum_delay_ms, base_delay_ms * 2 ** (attempt - 1))
    jitter = int.from_bytes(hashlib.sha256(f"{task}:{attempt}".encode()).digest()[:4], "big") % (raw // 4 + 1)
    delay = min(maximum_delay_ms, raw + jitter)
    return RetryProposal("retry", delay) if delay < remaining_ms else RetryProposal("deadline", 0)


@dataclass(frozen=True, slots=True)
class ShadowTask:
    ticket: str
    tenant: str
    arrival_ms: int
    duration_ms: int
    priority: int
    deadline_ms: int | None = None

    def __post_init__(self) -> None:
        identifier(self.ticket)
        identifier(self.tenant)
        bounded_int(self.arrival_ms, "arrival")
        bounded_int(self.duration_ms, "duration", 1)
        bounded_int(self.priority, "priority", 0, 1000)
        if self.deadline_ms is not None:
            bounded_int(self.deadline_ms, "deadline", self.arrival_ms)


@dataclass(frozen=True, slots=True)
class ShadowReceipt:
    policy: str
    trace_sha256: str
    timeline: tuple[tuple[str, int, int], ...]
    total_wait_ms: int
    p95_wait_ms: int
    deadline_misses: int
    max_wait_ms: int


def shadow_schedule(tasks: Sequence[ShadowTask], *, slots: int, policy: str) -> ShadowReceipt:
    """Deterministic nonpreemptive trace replay. It is not a deployed benchmark."""
    from heapq import heappush, heappop

    bounded_int(slots, "logical slots", 1, 256)
    if not 1 <= len(tasks) <= 2048 or policy not in ("fifo", "priority", "shortest", "fair_aging", "deadline"):
        raise DispatchPolicyError("invalid shadow configuration")
    if any(not isinstance(t, ShadowTask) for t in tasks) or len({t.ticket for t in tasks}) != len(tasks):
        raise DispatchPolicyError("invalid shadow tasks")
    arrivals = sorted(tasks, key=lambda t: (t.arrival_ms, t.ticket))
    trace = {
        "version": 1, "slots": slots, "policy": policy,
        "tasks": [[t.ticket, t.tenant, t.arrival_ms, t.duration_ms, t.priority, t.deadline_ms] for t in arrivals],
    }
    trace_sha = hashlib.sha256(json.dumps(trace, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    pending: list[ShadowTask] = []
    running: list[tuple[int, str, str]] = []
    active: dict[str, int] = {}
    timeline: list[tuple[str, int, int]] = []
    waiting_times: list[int] = []
    misses = 0
    i = 0
    now = arrivals[0].arrival_ms

    def key(t: ShadowTask) -> tuple:
        protected = t.priority <= 10
        floor = 0 if protected else 11
        slack = None if t.deadline_ms is None else t.deadline_ms - now - t.duration_ms
        base = (not protected,)
        tie = (t.arrival_ms, t.ticket)
        if policy == "fifo":
            return base + tie
        if policy == "priority":
            return base + (t.priority,) + tie
        if policy == "shortest":
            return base + (t.duration_ms,) + tie
        if policy == "deadline":
            return base + (slack is None, 0 if slack is None else slack, t.priority) + tie
        return base + (max(floor, t.priority - (now - t.arrival_ms) // 30_000),
                       active.get(t.tenant, 0)) + tie

    while i < len(arrivals) or pending or running:
        while running and running[0][0] <= now:
            _, _, tenant = heappop(running)
            active[tenant] -= 1
        while i < len(arrivals) and arrivals[i].arrival_ms <= now:
            pending.append(arrivals[i])
            i += 1
        while pending and len(running) < slots:
            task = min(pending, key=key)
            pending.remove(task)
            end = now + task.duration_ms
            timeline.append((task.ticket, now, end))
            waiting_times.append(now - task.arrival_ms)
            misses += int(task.deadline_ms is not None and end > task.deadline_ms)
            active[task.tenant] = active.get(task.tenant, 0) + 1
            heappush(running, (end, task.ticket, task.tenant))
        future = []
        if i < len(arrivals):
            future.append(arrivals[i].arrival_ms)
        if running:
            future.append(running[0][0])
        if not future:
            break
        now = min(future)
    waits = sorted(waiting_times)
    return ShadowReceipt(policy, trace_sha, tuple(timeline), sum(waits),
                         waits[(95 * len(waits) + 99) // 100 - 1], misses, waits[-1])


def choose_shadow(tasks: Sequence[ShadowTask], *, slots: int) -> tuple[ShadowReceipt, ...]:
    """Return all candidates ordered by missed deadlines then worst/tail/total wait.

    No policy is activated automatically; there is no access to real worker state.
    """
    receipts = [shadow_schedule(tasks, slots=slots, policy=p) for p in
                ("fifo", "priority", "shortest", "fair_aging", "deadline")]
    return tuple(sorted(receipts, key=lambda r: (r.deadline_misses, r.max_wait_ms, r.p95_wait_ms,
                                                 r.total_wait_ms, r.policy)))


@dataclass(frozen=True, slots=True)
class MeasuredShadow:
    policy: str
    workload_sha256: str
    timeline_sha256: str
    samples_ns: tuple[int, ...]
    median_ns: int
    p95_ns: int
    deadline_misses: int
    p95_wait_ms: int
    max_wait_ms: int


def measure_shadow_policies(tasks: Sequence[ShadowTask], *, slots: int,
                            repetitions: int = 5) -> tuple[MeasuredShadow, ...]:
    """Measure local scheduler computation against the same immutable trace.

    Report monotonic elapsed nanoseconds, not simulated task duration as
    observed throughput. Rotate policy order between rounds and retain all
    raw samples. Timeline consistency is checked across every repetition.
    This is an internal same-process microbenchmark, not an external
    competitor benchmark or a deployed worker throughput claim.
    """
    from time import perf_counter_ns

    bounded_int(repetitions, "repetitions", 1, 20)
    bounded_int(slots, "slots", 1, 256)
    if not 1 <= len(tasks) <= 2048 or any(not isinstance(t,ShadowTask) for t in tasks):
        raise DispatchPolicyError("invalid benchmark workload")
    frozen = tuple(sorted(tasks,key=lambda t:(t.arrival_ms,t.ticket)))
    if len({t.ticket for t in frozen}) != len(frozen):
        raise DispatchPolicyError("duplicate benchmark task")
    common = hashlib.sha256(json.dumps(
        ["measured-shadow-v1",slots,[[t.ticket,t.tenant,t.arrival_ms,t.duration_ms,
                                     t.priority,t.deadline_ms] for t in frozen]],
        separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
    policies=("fifo","priority","shortest","fair_aging","deadline")
    expected={p:shadow_schedule(frozen,slots=slots,policy=p) for p in policies}
    timings={p:[] for p in policies}
    for index in range(repetitions):
        offset=index%len(policies)
        for policy in policies[offset:]+policies[:offset]:
            start=perf_counter_ns()
            current=shadow_schedule(frozen,slots=slots,policy=policy)
            elapsed=perf_counter_ns()-start
            if elapsed<0 or current!=expected[policy]:
                raise DispatchPolicyError("benchmark clock or deterministic replay mismatch")
            timings[policy].append(elapsed)
    rows=[]
    for policy in policies:
        receipt=expected[policy]
        raw=tuple(timings[policy])
        ordered=sorted(raw)
        timeline_sha=hashlib.sha256(json.dumps(receipt.timeline,separators=(",",":")).encode()).hexdigest()
        rows.append(MeasuredShadow(policy,common,timeline_sha,raw,ordered[(len(raw)-1)//2],
                                   ordered[(95*len(raw)+99)//100-1],receipt.deadline_misses,
                                   receipt.p95_wait_ms,receipt.max_wait_ms))
    return tuple(rows)
