"""Authenticated, capacity-bound handoff for Dragon's pending recrawl orders.

This is a worker-session adapter, NOT a crawler/HTTP service. It never fetches
network content. Only a shared global resource grant and consented trusted
execution can produce a short-lived, checked worker ticket. The caller enforces
robots, egress, rights and all URL/response budgets before actual I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from skeleton.ai.webcrawler.dragon_resource_session import (
    DragonResourceSession, HardwareSample, SessionTask, plan_resources,
)
from .dragon_wisdom_pyramid import DragonWisdomPyramid, _hash, _id, _time


@dataclass(frozen=True, slots=True)
class RecrawlWorkerTicket:
    owner: str
    source_id: str
    source_revision: str
    order_digest: str
    task_id: str
    granted_at: int
    expires_at: int
    execution_authorized: bool = True

    def __post_init__(self) -> None:
        _id(self.owner)
        _id(self.source_id)
        _hash(self.source_revision)
        _hash(self.order_digest)
        _id(self.task_id)
        _time(self.granted_at)
        _time(self.expires_at)
        if not self.granted_at < self.expires_at <= self.granted_at + 300:
            raise ValueError("bounded worker grant lifetime required")
        if self.execution_authorized is not True:
            raise ValueError("worker ticket requires real grant")


class DragonRecrawlDispatcher:
    """One-process holder of real resource grants, with verified worker-stop.

    Production needs durable worker custody/lease recovery to resume after
    crashes; local SessionTask objects are not process-global leases.
    """

    def __init__(self, pyramid: DragonWisdomPyramid, session: DragonResourceSession):
        if not isinstance(pyramid, DragonWisdomPyramid):
            raise TypeError("canonical Wiki queue required")
        if not isinstance(session, DragonResourceSession):
            raise TypeError("canonical Dragon resource session required")
        self.pyramid = pyramid
        self.session = session
        self.lock = RLock()
        self.active: dict[str, RecrawlWorkerTicket] = {}
        self.stopped_tickets: dict[str, RecrawlWorkerTicket] = {}

    def _scope(self, owner: str, now: int, authorized: bool,
               trusted_worker: bool, consent: bool) -> None:
        if authorized is not True or trusted_worker is not True:
            raise PermissionError("authenticated trusted acquisition worker required")
        if consent is not True:
            raise PermissionError("current acquisition consent required")
        _id(owner)
        _time(now)
        if self.session.tenant != owner:
            raise PermissionError("resource session must be bound to identical owner")

    def _pending(self, owner: str, now: int) -> tuple[dict, ...]:
        return self.pyramid.recrawl_queue(
            owner, now=now, authorized=True, limit=128,
        )

    def preview(self, owner: str, sample: HardwareSample, *, now: int,
                authorized: bool, limit: int = 32) -> dict:
        """Read-only current recrawl work and resource-pressure preview.

        A preview does not reserve resources, admit a worker, fetch content,
        or approve the review/memory pyramid. Actual execution always enters
        begin() with a fresh trusted worker and explicit acquisition consent.
        """
        if authorized is not True:
            raise PermissionError("authenticated owner needed for recrawl preview")
        _id(owner)
        _time(now)
        if owner != self.session.tenant:
            raise PermissionError("recrawl preview must match session tenant")
        if not isinstance(sample, HardwareSample):
            raise ValueError("current typed hardware sample required")
        if type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError("bounded recrawl preview limit required")
        plan = plan_resources(sample, now=float(now), foreground=False)
        with self.lock:
            queue = self.pyramid.recrawl_queue(
                owner, now=now, authorized=True, limit=128,
            )
            rows = []
            for item in queue[:limit]:
                digest = item["order_digest"]
                ticket = self.active.get(digest)
                stopped = self.stopped_tickets.get(digest)
                current = (self.pyramid._latest_revision(owner, item["source_id"])
                           == item["revision"])
                rows.append({
                    "source_id": item["source_id"],
                    "source_revision": item["revision"],
                    "order_digest": digest,
                    "reason": item["reason"],
                    "priority": item["priority"],
                    "ordered_at": item["ordered_at"],
                    "source_revision_current": current,
                    "state": (
                        "active_worker" if ticket is not None else
                        "awaiting_independent_review" if stopped is not None else
                        "queued_unleased"
                    ),
                    "execution_authorized": False,
                    "memory_promotion_authorized": False,
                })
            return {
                "schema": "skeleton.dragon.recrawl_preview.v1",
                "owner": owner,
                "at": now,
                "pending_visible": len(rows),
                "pending_capped": len(queue) > limit or len(queue) == 128,
                "active_worker_count": len(self.active),
                "awaiting_review_count": len(self.stopped_tickets),
                "advisory_background_ready": plan.background_allowed,
                "advisory_reason": plan.reason,
                "items": rows,
                "execution_authorized": False,
                "network_io_performed": False,
                "memory_promotion_authorized": False,
            }

    def begin(self, owner: str, sample: HardwareSample, *, now: int,
              authorized: bool, trusted_worker: bool,
              consent: bool, memory_bytes: int = 8 * 1024 * 1024,
              io_tokens: int = 1) -> RecrawlWorkerTicket | None:
        """Reserve ONE currently pending refresh; no optimistic fake grants."""
        self._scope(owner, now, authorized, trusted_worker, consent)
        if not isinstance(sample, HardwareSample):
            raise ValueError("current hardware sample required")
        if type(memory_bytes) is not int or not 8 * 1024**2 <= memory_bytes <= 64 * 1024**2:
            raise ValueError("bounded declared worker memory required")
        if type(io_tokens) is not int or not 1 <= io_tokens <= 10000:
            raise ValueError("bounded declared I/O demand required")
        with self.lock:
            if len(self.active) + len(self.stopped_tickets) >= 64:
                raise ValueError("bounded unacknowledged recrawl worker budget exceeded")
            pending = self._pending(owner, now)
            for order in pending:
                digest = _hash(order["order_digest"])
                if digest in self.active or digest in self.stopped_tickets:
                    continue
                if self.pyramid._latest_revision(owner, order["source_id"]) != order["revision"]:
                    # A separate canonical import occurred; do not execute a
                    # request targeting a now-stale parent.
                    continue
                task_id = "recrawl:" + digest[:24]
                task = SessionTask(task_id, "acquisition", memory_bytes, 1,
                                   checkpointable=True, io_tokens=io_tokens)
                result = self.session.dispatch((task,), sample, now=float(now))
                if not result.execution_authorized or task_id not in result.admitted:
                    # The local scheduler can offer an advisory admission even
                    # when the shared global ledger is absent. Release that
                    # advisory reservation; it is NOT a worker grant.
                    if task_id in result.admitted:
                        self.session.stopped(task_id)
                    return None
                ticket = RecrawlWorkerTicket(
                    owner, order["source_id"], order["revision"],
                    digest, task_id, now, now + 60,
                )
                self.active[digest] = ticket
                return ticket
            return None

    def authorize_chunk(self, ticket: RecrawlWorkerTicket, sample: HardwareSample,
                        *, now: int, authorized: bool,
                        trusted_worker: bool, consent: bool) -> bool:
        """Revalidate owner, queue, current source revision and hardware per chunk.

        An expiring resource ticket does not bypass application egress policy.
        On false result the caller stops its worker and then calls stopped().
        """
        if not isinstance(ticket, RecrawlWorkerTicket) or not isinstance(sample, HardwareSample):
            raise TypeError("typed worker ticket and hardware required")
        self._scope(ticket.owner, now, authorized, trusted_worker, consent)
        with self.lock:
            if self.active.get(ticket.order_digest) != ticket:
                return False
            if not ticket.granted_at <= now < ticket.expires_at:
                return False
            plan = plan_resources(sample, now=float(now), foreground=False)
            if not plan.background_allowed or plan.memory_bytes == 0:
                return False
            if self.session.yield_requested(ticket.task_id):
                return False
            orders = self._pending(ticket.owner, now)
            if not any(row["order_digest"] == ticket.order_digest
                       and row["source_id"] == ticket.source_id
                       and row["revision"] == ticket.source_revision for row in orders):
                return False
            if self.pyramid._latest_revision(ticket.owner, ticket.source_id) != ticket.source_revision:
                return False
            return True

    def stopped(self, ticket: RecrawlWorkerTicket, *, authorized: bool,
                trusted_worker: bool, worker_stopped: bool) -> None:
        """Only a real stopped-worker acknowledgment releases global capacity."""
        if authorized is not True or trusted_worker is not True:
            raise PermissionError("trusted worker stop acknowledgment required")
        if worker_stopped is not True:
            raise PermissionError("stopping was requested, but not acknowledged")
        if not isinstance(ticket, RecrawlWorkerTicket):
            raise TypeError("typed ticket required")
        with self.lock:
            if self.active.get(ticket.order_digest) != ticket:
                raise ValueError("unknown or already stopped worker ticket")
            self.session.stopped(ticket.task_id)
            del self.active[ticket.order_digest]
            self.stopped_tickets[ticket.order_digest] = ticket

    def complete(self, ticket: RecrawlWorkerTicket, *, new_revision: str,
                 now: int, authorized: bool, trusted_worker: bool) -> dict:
        """Accept a separately reviewed canonical revision after worker stop.

        The underlying Almanac verifies expected parents and source custody.
        No received text or crawler self-assertion can satisfy that revision.
        """
        if authorized is not True or trusted_worker is not True:
            raise PermissionError("trusted source admission required")
        if not isinstance(ticket, RecrawlWorkerTicket):
            raise TypeError("typed ticket required")
        _time(now)
        _hash(new_revision)
        with self.lock:
            if self.stopped_tickets.get(ticket.order_digest) != ticket:
                raise ValueError("must acknowledge worker stop before completion")
            if now < ticket.granted_at:
                raise ValueError("completion clock predates worker grant")
            result = self.pyramid.complete_recrawl(
                ticket.owner, ticket.source_id, request_digest=ticket.order_digest,
                new_revision=new_revision, now=now, authorized=True,
                trusted_worker=True,
            )
            del self.stopped_tickets[ticket.order_digest]
            return result

    def abandon(self, ticket: RecrawlWorkerTicket, *, authorized: bool,
                trusted_worker: bool) -> None:
        """Discard a stopped attempt; the original recrawl order stays pending."""
        if authorized is not True or trusted_worker is not True:
            raise PermissionError("trusted stopped worker required")
        if not isinstance(ticket, RecrawlWorkerTicket):
            raise TypeError("typed ticket required")
        with self.lock:
            if self.stopped_tickets.get(ticket.order_digest) != ticket:
                raise ValueError("only an acknowledged stopped attempt can be abandoned")
            del self.stopped_tickets[ticket.order_digest]
