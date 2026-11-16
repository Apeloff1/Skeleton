"""Monotonic, cooperative offline iteration admission built on recovered owners.

The controller never executes a model. It publishes short-lived, single-use
admission proposals to a trusted in-process consumer. The consumer must
enforce resource budgets; a proposal cannot attest a completed kernel.
"""
from __future__ import annotations

from dataclasses import asdict
import threading
import time
from typing import Any

from skeleton.ai.model_runtime.iteration_scheduler import (
    InferencePhase, IterationScheduler, IterationWork,
)
from skeleton.app.offline_energy_budget import EnergyAdmission, EnergyPolicy
from skeleton.app.offline_energy_hysteresis import EnergyHysteresis, HysteresisPolicy
from skeleton.app.offline_runtime_preflight import (
    HardwareSample, ModelSource, RuntimePolicy, canonical, digest, integer,
    plan_preflight, require,
)

SCHEMA = "skeleton.offline.iteration-admission.v1"
MAX_WORK_ITEMS = 4096


def parse_work(raw: Any) -> tuple[IterationWork, ...]:
    require(type(raw) is list and len(raw) <= MAX_WORK_ITEMS, "bounded work list required")
    result = []
    seen = set()
    for row in raw:
        require(type(row) is dict and set(row) == {
            "request_id", "phase", "remaining_tokens", "priority", "age"
        }, "unexpected work fields")
        key = row["request_id"]
        require(type(key) is str and key.isascii() and 1 <= len(key) <= 128
                and all(ch.isalnum() or ch in "_-." for ch in key),
                "invalid request identity")
        require(key not in seen, "duplicate request identity")
        seen.add(key)
        require(row["phase"] in ("prefill", "decode"), "invalid inference phase")
        result.append(IterationWork(key, InferencePhase(row["phase"]),
                      integer(row["remaining_tokens"], 1, 1 << 31, "remaining tokens"),
                      integer(row["priority"], -10000, 10000, "priority"),
                      integer(row["age"], 0, 1 << 31, "age")))
    return tuple(result)


def _work_rows(work: tuple[IterationWork, ...]) -> list:
    require(type(work) is tuple and len(work) <= MAX_WORK_ITEMS, "bounded iteration work required")
    require(all(isinstance(row, IterationWork) for row in work), "typed iteration work required")
    rows = [{"request_id": row.request_id, "phase": row.phase.value,
             "remaining_tokens": row.remaining_tokens, "priority": row.priority,
             "age": row.age} for row in work]
    parse_work(rows)
    return rows


def _plan(work: tuple[IterationWork, ...], preflight: dict, workers: int, policy: RuntimePolicy) -> dict:
    """Use the canonical scheduler, then enforce the independent worker ceiling."""
    rows = _work_rows(work)
    scheduled = []
    scheduler_digest = None
    token_ceiling = 0
    if workers:
        pressure = preflight["pressure_fraction"]
        require(pressure is not None and 0 <= pressure < 1, "memory pressure not admissible")
        scheduler = IterationScheduler(token_budget=policy.maximum_tokens,
                                       prefill_quantum=policy.prefill_quantum)
        result = scheduler.plan_pressure_aware(work, measured_pressure_fraction=pressure,
                                               source="projected_memory_occupancy")
        scheduler_digest = result.digest
        token_ceiling = result.effective_token_budget
        scheduled = [{"request_id": item.request_id, "phase": item.phase.value, "tokens": item.tokens}
                     for item in result.plan.slices[:workers]]
    scheduled_ids = {row["request_id"] for row in scheduled}
    deferred = sorted(row["request_id"] for row in rows if row["request_id"] not in scheduled_ids)
    used = sum(row["tokens"] for row in scheduled)
    require(len(scheduled) <= workers and used <= token_ceiling, "scheduler exceeded admission")
    return {"work_digest": digest(rows), "scheduler_digest": scheduler_digest,
            "token_ceiling": token_ceiling, "scheduled_tokens": used,
            "slices": scheduled, "deferred": deferred}


class RuntimeAdmission:
    """In-process controller with immediate shedding, bounded recovery and CAS.

    The caller is a trusted local process. Direct dataclass inputs are not
    authenticated measurements. No receipt restores a grant after restart.
    No external process, GPU or RAM reservation is made by this class.
    """

    def __init__(self, source: ModelSource, policy: RuntimePolicy, *,
                 hysteresis_policy: HysteresisPolicy | None = None) -> None:
        require(isinstance(source, ModelSource) and isinstance(policy, RuntimePolicy),
                "validated source and policy required")
        self.source = source
        self.policy = policy
        self._source_digest = digest(source.snapshot())
        self._hysteresis = EnergyHysteresis(hysteresis_policy)
        self._sequence = 0
        self._last_sample = None
        self._last_origin = None
        self._pending = None
        self._lock = threading.RLock()

    def offer(self, sample: HardwareSample, work: tuple[IterationWork, ...], *,
              now_ns: int) -> dict:
        with self._lock:
            # A new offer always invalidates the previous unconsumed proposal.
            self._pending = None
            _work_rows(work)
            require(digest(self.source.snapshot()) == self._source_digest,
                    "selected source evidence changed")
            preflight = plan_preflight(self.source, sample, self.policy, now_ns=now_ns)
            if self._last_origin is not None and self._last_origin != sample.origin:
                # Simulated observations cannot prewarm the live admission gate.
                self._hysteresis = EnergyHysteresis(self._hysteresis.policy)
                self._last_sample = None
            self._last_origin = sample.origin
            chronological = self._last_sample is None or sample.started_ns > self._last_sample
            if not chronological or preflight["blockers"]:
                self._hysteresis = EnergyHysteresis(self._hysteresis.policy)
                hysteresis = None
                workers = 0
            else:
                raw = preflight["energy_plan"]
                candidate = EnergyAdmission(raw["allowed_workers"], raw["base_workers"],
                                            raw["reason"], raw["digest"], sample.power, EnergyPolicy())
                observed = self._hysteresis.step(candidate, now_ns=now_ns,
                                                  sampled_ns=sample.started_ns)
                hysteresis = asdict(observed)
                workers = min(preflight["worker_ceiling"], observed.admitted_workers)
            if chronological and preflight["fresh"]:
                self._last_sample = sample.started_ns
            result = _plan(work, preflight, workers, self.policy)
            self._sequence += 1
            blockers = list(preflight["blockers"])
            if not chronological:
                blockers.append("replayed_or_nonadvancing_hardware_sample")
            if not workers and not blockers:
                blockers.append("recovery_hysteresis")
            body = {"schema": SCHEMA, "sequence": self._sequence,
                    "source_digest": self._source_digest,
                    "preflight_digest": preflight["preflight_digest"],
                    "sample_origin": sample.origin, "issued_ns": now_ns,
                    "expires_ns": sample.started_ns + self.policy.sample_age_ns,
                    "worker_ceiling": workers, "hysteresis": hysteresis,
                    "blockers": blockers, **result,
                    "status": "candidate" if result["slices"] else "no_grant",
                    "model_activation": "not_performed", "native_qualified": False,
                    "release_qualified": False}
            receipt = {**body, "admission_digest": digest(body)}
            canonical(receipt)
            if result["slices"]:
                self._pending = receipt
            # Return detached data so callers cannot alter a pending proposal.
            import json
            return {"preflight": preflight, "admission": json.loads(canonical(receipt))}

    def consume(self, receipt: dict, *, now_ns: int) -> tuple[dict, ...]:
        """Consume exactly one local-probe proposal; never issue a new one."""
        with self._lock:
            integer(now_ns, 0, 2**63-1, "consumption timestamp")
            pending = self._pending
            self._pending = None  # any failed consumption also invalidates it
            require(pending is not None, "no pending iteration proposal")
            require(type(receipt) is dict and canonical(receipt) == canonical(pending),
                    "proposal differs from exact pending admission")
            require(pending["sample_origin"] == "local_probe", "fixture cannot authorize consumption")
            require(pending["issued_ns"] <= now_ns <= pending["expires_ns"],
                    "iteration proposal is stale or future")
            require(digest(self.source.snapshot()) == self._source_digest, "selected model source changed")
            return tuple(dict(row) for row in pending["slices"])

    def revoke(self) -> None:
        """Drop all grants and recovery history immediately."""
        with self._lock:
            self._pending = None
            self._hysteresis = EnergyHysteresis(self._hysteresis.policy)

    def status(self) -> dict:
        with self._lock:
            return {"sequence": self._sequence, "source_digest": self._source_digest,
                    "pending": self._pending is not None, "hysteresis_workers": self._hysteresis.workers,
                    "sample_origin": self._last_origin,
                    "native_qualified": False, "release_qualified": False}
