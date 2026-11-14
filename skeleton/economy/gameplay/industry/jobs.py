"""Build and research jobs and the tick-driven per-owner build queue.

Jobs never read the wall clock. A job is *queued* until its dependencies
are delivered, a production line is free and (for builds) its materials are
on hand; it then *runs* from ``start`` to ``end = start + ticks``. The
queue only orders and times jobs; :class:`~.engine.IndustrySystem` moves
money and items.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

BUILD = "build"
RESEARCH = "research"
KINDS = (BUILD, RESEARCH)

QUEUED = "queued"
RUNNING = "running"
DONE = "done"  # finished, output waiting for delivery (bags were full)
DELIVERED = "delivered"
CANCELLED = "cancelled"
STATUSES = (QUEUED, RUNNING, DONE, DELIVERED, CANCELLED)
MAX_JOBS = 100_000
MAX_JOB_ID = (1 << 63) - 1


@dataclass
class Job:
    job_id: int
    owner: str
    kind: str
    blueprint_id: str
    runs: int = 1
    track: str = ""
    deps: tuple[int, ...] = ()
    chain_id: int | None = None
    created: int = 0
    status: str = QUEUED
    start: int | None = None
    end: int | None = None
    me: int = 0
    te: int = 0
    used: dict[str, int] = field(default_factory=dict)
    lost: dict[str, int] = field(default_factory=dict)
    output: str = ""
    output_qty: int = 0
    fee: int = 0

    @property
    def active(self) -> bool:
        return self.status in (QUEUED, RUNNING)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "owner": self.owner,
            "kind": self.kind,
            "blueprint_id": self.blueprint_id,
            "runs": self.runs,
            "track": self.track,
            "deps": list(self.deps),
            "chain_id": self.chain_id,
            "created": self.created,
            "status": self.status,
            "start": self.start,
            "end": self.end,
            "me": self.me,
            "te": self.te,
            "used": dict(sorted(self.used.items())),
            "lost": dict(sorted(self.lost.items())),
            "output": self.output,
            "output_qty": self.output_qty,
            "fee": self.fee,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Job":
        kw = dict(data)
        for key in ("job_id", "runs", "created", "me", "te", "output_qty", "fee"):
            value = kw[key]
            minimum = 1 if key in ("job_id", "runs") else 0
            if type(value) is not int or not minimum <= value <= (1 << 63) - 1:
                raise ValueError("invalid saved job counter")
        for key in ("owner", "blueprint_id"):
            if type(kw[key]) is not str or not kw[key] or len(kw[key]) > 256:
                raise ValueError("invalid saved job identity")
        if kw["kind"] not in KINDS or kw["status"] not in STATUSES:
            raise ValueError("invalid saved job kind or status")
        if kw["kind"] == RESEARCH and kw["track"] not in ("me", "te"):
            raise ValueError("invalid saved research track")
        if kw["kind"] == BUILD and (kw["track"] != "" or type(kw["output"]) is not str
                                    or not kw["output"] or kw["output_qty"] < 1):
            raise ValueError("invalid saved build output")
        chain = kw["chain_id"]
        if chain is not None and (type(chain) is not int or not 1 <= chain <= (1 << 63) - 1):
            raise ValueError("invalid saved chain identity")
        deps = kw["deps"]
        if type(deps) not in (tuple, list) or len(deps) > 10_000 or any(
            type(d) is not int or not 1 <= d < kw["job_id"] for d in deps
        ) or len(set(deps)) != len(deps):
            raise ValueError("invalid saved job dependencies")
        kw["deps"] = tuple(deps)
        for key in ("used", "lost"):
            if type(kw[key]) is not dict or any(
                type(k) is not str or not k or type(v) is not int or not 0 <= v <= (1 << 63) - 1
                for k, v in kw[key].items()
            ):
                raise ValueError("invalid saved job materials")
            kw[key] = dict(kw[key])
        start, end = kw["start"], kw["end"]
        if kw["status"] in (QUEUED, CANCELLED):
            if start is not None or end is not None:
                raise ValueError("unstarted job has execution timestamps")
        elif (type(start) is not int or type(end) is not int
              or not kw["created"] <= start < end <= (1 << 63) - 1):
            raise ValueError("invalid saved running job timestamps")
        return cls(**kw)


class BuildQueue:
    """All jobs, in id order, plus per-owner line counts."""

    def __init__(self, default_lines: int = 2) -> None:
        if default_lines < 1:
            raise ValueError("default_lines must be >= 1")
        self.default_lines = default_lines
        self.lines: dict[str, int] = {}
        self.jobs: dict[int, Job] = {}
        self.next_id = 1

    def require_capacity(self, count: int = 1) -> None:
        if type(count) is not int or count < 0 or len(self.jobs) + count > MAX_JOBS:
            raise ValueError("production job history capacity exceeded")
        if self.next_id + count > MAX_JOB_ID:
            raise ValueError("production job identity exhausted")

    def add(self, job: Job) -> Job:
        if len(self.jobs) >= MAX_JOBS:
            raise ValueError("production job history capacity exceeded")
        if type(job.job_id) is not int or not 1 <= job.job_id < MAX_JOB_ID:
            raise ValueError("invalid production job identity")
        if job.job_id in self.jobs:
            raise ValueError("duplicate job identity")
        self.jobs[job.job_id] = job
        self.next_id = max(self.next_id, job.job_id + 1)
        return job

    def new_id(self) -> int:
        self.require_capacity()
        jid = self.next_id
        self.next_id += 1
        return jid

    def lines_of(self, owner: str) -> int:
        return self.lines.get(owner, self.default_lines)

    def running(self, owner: str | None = None) -> list[Job]:
        return [
            j
            for j in self.ordered()
            if j.status == RUNNING and (owner is None or j.owner == owner)
        ]

    def queued(self) -> list[Job]:
        return [j for j in self.ordered() if j.status == QUEUED]

    def ordered(self) -> list[Job]:
        return [self.jobs[k] for k in sorted(self.jobs)]

    def of(self, owner: str) -> list[Job]:
        return [j for j in self.ordered() if j.owner == owner]

    def next_completion(self, until: int) -> Job | None:
        due = [
            j
            for j in self.jobs.values()
            if j.status == RUNNING and j.end is not None and j.end <= until
        ]
        return min(due, key=lambda j: (j.end, j.job_id)) if due else None

    def deps_ready(self, job: Job) -> bool:
        return all(self.jobs[d].status == DELIVERED for d in job.deps)

    def deps_failed(self, job: Job) -> bool:
        return any(self.jobs[d].status == CANCELLED for d in job.deps)

    def free_line(self, owner: str) -> bool:
        return len(self.running(owner)) < self.lines_of(owner)

    def pending_research(self, owner: str, blueprint_id: str, track: str) -> int:
        return sum(
            1
            for j in self.jobs.values()
            if j.kind == RESEARCH
            and j.active
            and j.owner == owner
            and j.blueprint_id == blueprint_id
            and j.track == track
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "default_lines": self.default_lines,
            "lines": dict(sorted(self.lines.items())),
            "jobs": [j.to_dict() for j in self.ordered()],
            "next_id": self.next_id,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "BuildQueue":
        if type(state["default_lines"]) is not int or not 1 <= state["default_lines"] <= 10_000:
            raise ValueError("invalid default production lines")
        q = cls(state["default_lines"])
        if type(state["lines"]) is not dict or any(
            type(k) is not str or not k or type(v) is not int or not 1 <= v <= 10_000
            for k, v in state["lines"].items()
        ):
            raise ValueError("invalid saved production lines")
        q.lines = dict(state["lines"])
        if type(state["jobs"]) is not list or len(state["jobs"]) > 100_000:
            raise ValueError("saved job inventory exceeds budget")
        for row in state["jobs"]:
            q.add(Job.from_dict(row))
        for job in q.jobs.values():
            for dependency in job.deps:
                parent = q.jobs.get(dependency)
                if (parent is None or parent.owner != job.owner
                        or job.chain_id is None or parent.chain_id != job.chain_id):
                    raise ValueError("invalid saved job dependency custody")
                if job.status in (RUNNING, DONE, DELIVERED) and parent.status != DELIVERED:
                    raise ValueError("started job has incomplete dependency")
        next_id = state["next_id"]
        if type(next_id) is not int or not q.next_id <= next_id <= (1 << 63) - 1:
            raise ValueError("invalid next job identity")
        q.next_id = next_id
        return q


def chain_ids(jobs: Iterable[Job]) -> list[int]:
    return sorted({j.chain_id for j in jobs if j.chain_id is not None})


__all__ = [
    "BUILD",
    "CANCELLED",
    "DELIVERED",
    "DONE",
    "KINDS",
    "QUEUED",
    "RESEARCH",
    "RUNNING",
    "STATUSES",
    "BuildQueue",
    "Job",
    "MAX_JOBS",
    "chain_ids",
]
