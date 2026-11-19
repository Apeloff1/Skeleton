"""Explicit local worker computation with durable, authenticated results.

Handlers are app-owned reviewed callables. They must be computation-only:
no external side effects, subprocess, arbitrary file writes or network.
The adapter cannot sandbox Python callables. The journal remains the sole
authority for admission; the result database is the sole result owner.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Awaitable, Callable

from skeleton.frontier.durable_work import DurableWorkJournal, WorkClaim, WorkConflict
from skeleton.frontier.payloads import json_snapshot
from skeleton.frontier.worker_results import WorkerResultStore, input_digest, encode_result
from skeleton.prood.supervisor import WorkerOutcome


@dataclass(frozen=True, slots=True)
class WorkerInput:
    work_id: str
    plan_hash: str
    build_id: str
    phase: str
    role: str
    seat: int
    seed: int
    game_context: dict
    dependency_results: tuple[tuple[str, object], ...]


@dataclass(frozen=True, slots=True)
class ComputedResult:
    succeeded: bool
    output: object


Handler = Callable[[WorkerInput], Awaitable[ComputedResult]]


def verified_predecessors(journal: DurableWorkJournal, results: WorkerResultStore,
                          dependencies: tuple[str, ...]) -> tuple[tuple[str, object], ...]:
    if journal.scope != results.scope:
        raise WorkConflict("worker result scope mismatch")
    predecessors = []
    total = 0
    for dep in dependencies:
        upstream = journal.status(dep)
        result = results.load(dep)
        if (upstream.state != "succeeded" or result is None or not result.succeeded
                or upstream.receipt != result.receipt_digest):
            raise WorkConflict("dependency lacks matching durable worker result")
        total += len(encode_result(result.output))
        if total > 1 << 20:
            raise WorkConflict("aggregate dependency output exceeds worker input budget")
        predecessors.append((dep, result.output))
    return tuple(predecessors)


def worker_input_digest(body, predecessors):
    return input_digest([body, [[wid, value] for wid, value in predecessors]])


class LocalWorkerExecutor:
    """Bind one planned context and closed handler catalog to a result store."""

    def __init__(self, journal: DurableWorkJournal, results: WorkerResultStore, *,
                 game_context: dict, handlers: dict[str, Handler]):
        if type(journal) is not DurableWorkJournal or type(results) is not WorkerResultStore:
            raise TypeError("canonical work and result custody required")
        if journal.scope != results.scope:
            raise WorkConflict("worker result scope mismatch")
        if type(game_context) is not dict:
            raise ValueError("explicit game context required")
        if type(handlers) is not dict or not 1 <= len(handlers) <= 32:
            raise ValueError("bounded explicit worker handlers required")
        for role, handler in handlers.items():
            if type(role) is not str or not role or len(role) > 128 or not callable(handler):
                raise ValueError("invalid worker handler")
        self._journal, self._results = journal, results
        self._context = json_snapshot(game_context, max_bytes=262144)
        self._context_digest = sha256(json.dumps(
            self._context, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")).hexdigest()
        self._handlers = MappingProxyType(dict(handlers))
        self._active = False

    def accepts(self, work_id: str) -> bool:
        """Reject incompatible plan contexts and unsupported roles before claiming."""
        body = self._journal.pending_payload(work_id, kind="prood.worker")
        return self._compatible(body)

    def _compatible(self, body):
        return (type(body) is dict and body.get("schema") == "prood.worker.v1"
                and body.get("context_digest") == self._context_digest
                and body.get("execution_verified") is False
                and type(body.get("role")) is str and body["role"] in self._handlers)

    async def execute_and_commit(self, claim: WorkClaim) -> WorkerOutcome:
        if self._active:
            raise WorkConflict("local worker already executing")
        self._active = True
        try:
            body = self._journal.verify_claim(claim, kind="prood.worker")
            if not self._compatible(body):
                raise WorkConflict("worker plan context or role does not match admitted input")
            role = body["role"]
            status = self._journal.status(claim.work_id)
            predecessors = verified_predecessors(self._journal, self._results, status.dependencies)
            digest = worker_input_digest(body, predecessors)
            previous = self._results.load(claim.work_id)
            if previous is not None:
                # A crash between result commit and journal settlement cannot
                # trigger recomputation. The exact authenticated result is reused.
                if previous.input_digest != digest:
                    raise WorkConflict("stored result input differs")
                return WorkerOutcome(claim.work_id, previous.succeeded, previous.receipt_digest)
            worker = WorkerInput(claim.work_id, body["plan_hash"], body["build_id"],
                                 body["phase"], role, body["seat"], body["seed"],
                                 json_snapshot(self._context, max_bytes=262144),
                                 tuple(predecessors))
            computed = await self._handlers[role](worker)
            if type(computed) is not ComputedResult or type(computed.succeeded) is not bool:
                raise WorkConflict("worker did not return a canonical outcome")
            self._journal.verify_claim(claim, kind="prood.worker")
            stored = self._results.publish(claim.work_id, digest=digest,
                                           succeeded=computed.succeeded, output=computed.output)
            return WorkerOutcome(claim.work_id, stored.succeeded, stored.receipt_digest)
        finally:
            self._active = False
