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
        kw["deps"] = tuple(int(d) for d in kw.get("deps", ()))
        kw["used"] = {k: int(v) for k, v in kw.get("used", {}).items()}
        kw["lost"] = {k: int(v) for k, v in kw.get("lost", {}).items()}
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

    def add(self, job: Job) -> Job:
        self.jobs[job.job_id] = job
        self.next_id = max(self.next_id, job.job_id + 1)
        return job

    def new_id(self) -> int:
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
        q = cls(int(state["default_lines"]))
        q.lines = {k: int(v) for k, v in state["lines"].items()}
        for row in state["jobs"]:
            q.add(Job.from_dict(row))
        q.next_id = int(state["next_id"])
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
    "chain_ids",
]
