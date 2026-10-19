"""Deterministic milestone work-queue with scoped leases and restart receipts.

No implicit background thread, shell invocation, network access or unbounded
retry. The host supplies a monotonic clock, durable storage and independently
configured workbench checkers. Queue snapshots remain source-bound and can
be restored only after their event hash-chain is verified.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from .delivery_assurance_milestones import (
    ASSURANCE_MILESTONES, MILESTONE_INDEX, MilestoneBoard,
    verify_milestone_board,
)
from .delivery_milestone_workbench import (
    ExecutionVerdict, HostChecker, evaluate_milestone,
)
from .types import stable_fingerprint

_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OWNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_ALLOWED = {"pending", "leased", "passed", "failed"}


class QueueContractError(ValueError):
    """Milestone scheduler input, lease or durable state violated its contract."""


@dataclass(frozen=True, slots=True)
class WorkItem:
    milestone_id: str
    status: str
    attempts: int = 0
    priority: int = 0
    owner: str | None = None
    lease_expires: float | None = None
    lease_serial: str | None = None
    retry_after: float = 0.0
    last_failure: str = ""

    def __post_init__(self) -> None:
        if self.milestone_id not in MILESTONE_INDEX:
            raise QueueContractError("invalid work item milestone")
        if self.status not in _ALLOWED:
            raise QueueContractError("unknown work status")
        if type(self.attempts) is not int or not 0 <= self.attempts <= 1_000_000:
            raise QueueContractError("invalid retry counter")
        if type(self.priority) is not int or not -10_000 <= self.priority <= 10_000:
            raise QueueContractError("invalid work priority")
        if not isinstance(self.retry_after, (int, float)) or not math.isfinite(self.retry_after) or self.retry_after < 0:
            raise QueueContractError("invalid retry-after clock")
        if not isinstance(self.last_failure, str) or len(self.last_failure) > 512:
            raise QueueContractError("invalid failure diagnostic")
        if self.status == "leased":
            if (not isinstance(self.owner, str) or not _OWNER.fullmatch(self.owner)
                    or not isinstance(self.lease_serial, str) or not self.lease_serial
                    or not isinstance(self.lease_expires, (int, float))
                    or not math.isfinite(self.lease_expires) or self.lease_expires <= 0):
                raise QueueContractError("active lease needs owner, token and finite expiration")
        elif self.owner is not None or self.lease_expires is not None or self.lease_serial is not None:
            raise QueueContractError("nonleased work item retains a stale lease")


@dataclass(frozen=True, slots=True)
class QueueEvent:
    sequence: int
    milestone_id: str
    action: str
    subject: str
    previous: str
    digest: str

    @classmethod
    def create(
        cls, sequence: int, milestone_id: str, action: str,
        subject: str, previous: str,
    ) -> "QueueEvent":
        if (type(sequence) is not int or sequence < 1 or
                milestone_id not in MILESTONE_INDEX):
            raise QueueContractError("invalid queue event identity")
        if action not in {"claim", "pass", "retry", "fail", "expire"}:
            raise QueueContractError("invalid queue event type")
        if not _SHA256.fullmatch(subject) or not _SHA256.fullmatch(previous):
            raise QueueContractError("invalid queue event hash source")
        digest = stable_fingerprint({
            "sequence": sequence, "milestone": milestone_id,
            "action": action, "subject": subject, "previous": previous,
        })
        return cls(sequence, milestone_id, action, subject, previous, digest)


@dataclass(frozen=True, slots=True)
class WorkLease:
    milestone_id: str
    owner: str
    serial: str
    expires_at: float
    source_commit: str
    artifact_digest: str


@dataclass(frozen=True, slots=True)
class MilestoneQueue:
    source_commit: str
    artifact_digest: str
    max_attempts: int
    lease_seconds: float
    board: MilestoneBoard
    work: tuple[WorkItem, ...]
    events: tuple[QueueEvent, ...] = ()

    @classmethod
    def start(
        cls, source_commit: str, artifact_digest: str,
        *, max_attempts: int = 3, lease_seconds: float = 120.0,
        priorities: Mapping[str, int] | None = None,
    ) -> "MilestoneQueue":
        if not isinstance(source_commit, str) or not _SHA1.fullmatch(source_commit):
            raise QueueContractError("queue source must pin an exact commit")
        if not isinstance(artifact_digest, str) or not _SHA256.fullmatch(artifact_digest):
            raise QueueContractError("queue requires content source hash")
        if type(max_attempts) is not int or not 1 <= max_attempts <= 50:
            raise QueueContractError("retry policy outside bounded range")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, (int, float)) or not math.isfinite(lease_seconds) or not 1 <= lease_seconds <= 86_400:
            raise QueueContractError("lease duration outside bounded range")
        priority = dict(priorities or {})
        if any(k not in MILESTONE_INDEX for k in priority):
            raise QueueContractError("unknown priority milestone")
        work = tuple(WorkItem(
            milestone_id=m.code, status="pending",
            priority=priority.get(m.code, 0),
        ) for m in ASSURANCE_MILESTONES)
        queue = cls(source_commit, artifact_digest, max_attempts,
                    float(lease_seconds), MilestoneBoard.begin(source_commit), work)
        verify_queue(queue)
        return queue

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "source": self.source_commit, "artifact": self.artifact_digest,
            "max_attempts": self.max_attempts, "lease_seconds": self.lease_seconds,
            "board": self.board.fingerprint,
            "work": [vars_for_item(item) for item in self.work],
            "events": [event.digest for event in self.events],
        })

    def get(self, milestone_id: str) -> WorkItem:
        if milestone_id not in MILESTONE_INDEX:
            raise QueueContractError("unknown milestone")
        return self.work[int(milestone_id[1:]) - 1]

    def _replace_item(
        self, item: WorkItem, action: str, *,
        event_subject: str | None = None,
        board: MilestoneBoard | None = None,
    ) -> "MilestoneQueue":
        index = int(item.milestone_id[1:]) - 1
        items = list(self.work)
        items[index] = item
        previous = self.events[-1].digest if self.events else "0" * 64
        subject = event_subject or stable_fingerprint(vars_for_item(item))
        event = QueueEvent.create(
            len(self.events) + 1, item.milestone_id, action,
            subject, previous,
        )
        return replace(
            self, board=self.board if board is None else board,
            work=tuple(items), events=self.events + (event,),
        )

    def ready(self, now: float) -> tuple[str, ...]:
        verify_queue(self)
        clock = _clock(now)
        eligible = []
        for item in self.work:
            prerequisite = MILESTONE_INDEX[item.milestone_id].prerequisite
            if (item.status == "pending" and item.retry_after <= clock
                    and (prerequisite is None or prerequisite in self.board.passing)):
                eligible.append(item)
        eligible.sort(key=lambda x: (-x.priority, x.attempts, x.milestone_id))
        return tuple(item.milestone_id for item in eligible)

    def claim(self, owner: str, now: float) -> tuple["MilestoneQueue", WorkLease | None]:
        verify_queue(self)
        clock = _clock(now)
        if not isinstance(owner, str) or not _OWNER.fullmatch(owner):
            raise QueueContractError("invalid lease owner")
        options = self.ready(clock)
        if not options:
            return self, None
        item = self.get(options[0])
        serial = stable_fingerprint({
            "queue": self.fingerprint, "owner": owner,
            "milestone": item.milestone_id, "attempt": item.attempts + 1,
            "time": clock,
        })
        expires = clock + self.lease_seconds
        updated = replace(
            item, status="leased", attempts=item.attempts + 1,
            owner=owner, lease_expires=expires, lease_serial=serial,
        )
        result = self._replace_item(updated, "claim")
        verify_queue(result)
        return result, WorkLease(
            item.milestone_id, owner, serial, expires,
            self.source_commit, self.artifact_digest,
        )

    def settle(
        self,
        lease: WorkLease,
        now: float,
        primary: HostChecker | None,
        independent: HostChecker | None,
        *,
        retry_seconds: float = 30,
    ) -> tuple["MilestoneQueue", ExecutionVerdict]:
        verify_queue(self)
        clock = _clock(now)
        if not isinstance(lease, WorkLease):
            raise QueueContractError("host must present typed lease")
        item = self.get(lease.milestone_id)
        if (item.status != "leased" or item.owner != lease.owner
                or item.lease_serial != lease.serial
                or item.lease_expires != lease.expires_at
                or lease.source_commit != self.source_commit
                or lease.artifact_digest != self.artifact_digest):
            raise QueueContractError("stale, foreign or forged lease token")
        if clock >= lease.expires_at:
            raise QueueContractError("lease expired before result authorization")
        if (isinstance(retry_seconds, bool) or
                not isinstance(retry_seconds, (int, float)) or
                not math.isfinite(retry_seconds) or not 0 <= retry_seconds <= 86_400):
            raise QueueContractError("invalid bounded retry interval")
        result = evaluate_milestone(
            lease.milestone_id, self.source_commit, self.artifact_digest,
            primary, independent,
        )
        if result.passed:
            new_board = self.board.register(result.attestation)
            updated = replace(
                item, status="passed", owner=None, lease_expires=None,
                lease_serial=None, last_failure="",
            )
            next_queue = self._replace_item(
                updated, "pass", event_subject=result.fingerprint,
                board=new_board,
            )
        else:
            exhausted = item.attempts >= self.max_attempts
            updated = replace(
                item, status="failed" if exhausted else "pending",
                owner=None, lease_expires=None, lease_serial=None,
                retry_after=clock + float(retry_seconds),
                last_failure=result.detail[:512],
            )
            next_queue = self._replace_item(
                updated, "fail" if exhausted else "retry",
                event_subject=result.fingerprint,
            )
        verify_queue(next_queue)
        return next_queue, result

    def expire(self, now: float, *, retry_seconds: float = 30) -> "MilestoneQueue":
        """Recover abandoned work after crashes, never reusing its old lease."""
        verify_queue(self)
        clock = _clock(now)
        if (isinstance(retry_seconds, bool) or
                not isinstance(retry_seconds, (int, float)) or
                not math.isfinite(retry_seconds) or not 0 <= retry_seconds <= 86_400):
            raise QueueContractError("invalid recovery interval")
        current = self
        for item in self.work:
            if item.status != "leased" or item.lease_expires > clock:
                continue
            exhausted = item.attempts >= current.max_attempts
            updated = replace(
                item, status="failed" if exhausted else "pending",
                owner=None, lease_expires=None, lease_serial=None,
                retry_after=clock + float(retry_seconds),
                last_failure="lease expired before verified settlement",
            )
            current = current._replace_item(updated, "expire")
        verify_queue(current)
        return current

    def summary(self) -> dict[str, object]:
        verify_queue(self)
        counts = {state: sum(item.status == state for item in self.work)
                  for state in _ALLOWED}
        return {
            "source_commit": self.source_commit,
            "artifact_digest": self.artifact_digest,
            "completed": counts["passed"],
            "pending": counts["pending"],
            "leased": counts["leased"],
            "failed": counts["failed"],
            "target": 100,
            "completion_percent": counts["passed"],
            "event_count": len(self.events),
            "receipt": self.fingerprint,
        }


def _clock(now: float) -> float:
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0:
        raise QueueContractError("host must provide finite monotonic time")
    return float(now)


def vars_for_item(item: WorkItem) -> dict[str, object]:
    return {
        "id": item.milestone_id, "status": item.status,
        "attempts": item.attempts, "priority": item.priority,
        "owner": item.owner, "expiry": item.lease_expires,
        "lease": item.lease_serial, "retry": item.retry_after,
        "failure": item.last_failure,
    }


def verify_queue(queue: MilestoneQueue) -> None:
    if (len(queue.work) != 100 or
            tuple(item.milestone_id for item in queue.work) != tuple(
                x.code for x in ASSURANCE_MILESTONES
            )):
        raise QueueContractError("queue lost or reordered milestone work")
    if not _SHA1.fullmatch(queue.source_commit) or not _SHA256.fullmatch(queue.artifact_digest):
        raise QueueContractError("queue source identity invalid")
    if queue.board.source_commit != queue.source_commit:
        raise QueueContractError("milestone board switched source commits")
    if type(queue.max_attempts) is not int or not 1 <= queue.max_attempts <= 50:
        raise QueueContractError("invalid restored retry budget")
    if (not isinstance(queue.lease_seconds, (int, float))
            or not math.isfinite(queue.lease_seconds)
            or not 1 <= queue.lease_seconds <= 86_400):
        raise QueueContractError("invalid restored lease duration")
    verify_milestone_board(queue.board)
    active_tokens = set()
    for item in queue.work:
        item.__post_init__()
        if item.attempts > queue.max_attempts:
            raise QueueContractError("work item exceeded retry budget")
        if (item.status == "passed") != (item.milestone_id in queue.board.passing):
            raise QueueContractError("queue pass state differs from verified board")
        if item.status == "leased":
            if item.lease_serial in active_tokens:
                raise QueueContractError("duplicate lease token")
            active_tokens.add(item.lease_serial)
    previous = "0" * 64
    for i, item in enumerate(queue.events, 1):
        if item != QueueEvent.create(
            i, item.milestone_id, item.action, item.subject, previous,
        ):
            raise QueueContractError("queue event chain was modified")
        previous = item.digest


def restore_queue(snapshot: MilestoneQueue, expected_commit: str,
                  expected_artifact: str) -> MilestoneQueue:
    """Fail closed on rollback or stale-source restart."""
    verify_queue(snapshot)
    if (snapshot.source_commit != expected_commit
            or snapshot.artifact_digest != expected_artifact):
        raise QueueContractError("restored queue does not match host source bytes")
    return snapshot
