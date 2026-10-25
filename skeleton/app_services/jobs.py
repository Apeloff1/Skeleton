"""Durable SQLite job queue for long game builds, plus a build worker.

Lease-based at-least-once delivery: ``claim`` atomically leases the oldest
ready job; expired leases are reclaimable; ``fail`` retries with backoff until
``max_attempts`` and then dead-letters (status ``dead``).

Event emit points (envelope v1, see ``events.py``) all go through
``BuildJobRunner._emit`` -> ``JobEventPublisher.publish``.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable, Mapping, Optional, Sequence

from skeleton.persistence.app_foundation.db import Database
from skeleton.app_services.events import (
    JobEventPublisher,
    NullJobEventPublisher,
    make_envelope,
)
from skeleton.app_services.ports import Build, BuildRepository, Job
from skeleton.observability.redaction import safe_exception_text

JOB_STATUSES = ("queued", "running", "succeeded", "failed", "dead", "cancelled")
BUILD_JOB_KIND = "game.build"


class LeaseLost(RuntimeError):
    pass


class OwnedJobConflict(ValueError):
    """An existing job cannot prove the submitted owner/body binding."""


class SqliteJobQueue:
    def __init__(self, db: Database, *, clock: Callable[[], float] = time.time) -> None:
        self.db, self.clock = db, clock

    @staticmethod
    def _job(r: Any) -> Job:
        return Job(r["job_id"], r["kind"], r["status"], json.loads(r["payload"]), r["attempts"],
                   r["max_attempts"], r["run_after"], r["created_at"], r["updated_at"],
                   r["lease_owner"], r["lease_expires_at"], r["correlation_id"], r["progress"],
                   json.loads(r["result"]), r["error"])

    def get(self, job_id: str) -> Optional[Job]:
        rows = self.db.query("SELECT * FROM jobs WHERE job_id=?", (job_id,))
        return self._job(rows[0]) if rows else None

    def get_by_idempotency_key(self, key: str) -> Optional[Job]:
        rows = self.db.query("SELECT * FROM jobs WHERE idempotency_key=?", (key,))
        return self._job(rows[0]) if rows else None

    def enqueue(self, kind: str, payload: Mapping[str, Any], *, max_attempts: int = 3,
                delay_s: float = 0.0, correlation_id: str = "",
                idempotency_key: Optional[str] = None) -> Job:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        now = self.clock()
        if idempotency_key:
            rows = self.db.query("SELECT * FROM jobs WHERE idempotency_key=?", (idempotency_key,))
            if rows:
                return self._job(rows[0])
        jid = f"job_{uuid.uuid4().hex}"
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO jobs (job_id, kind, status, payload, max_attempts, run_after,"
                " correlation_id, idempotency_key, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (jid, kind, "queued", json.dumps(dict(payload), sort_keys=True), max_attempts,
                 now + delay_s, correlation_id, idempotency_key, now, now))
        return self.get(jid)  # type: ignore[return-value]

    def enqueue_owned(self, kind: str, payload: Mapping[str, Any], *, actor_id: str,
                      tenant_id: str, request_hash: str, timeout_s: float,
                      execution_id: Optional[str] = None, project_id: Optional[str] = None,
                      idempotency_key: Optional[str] = None, legacy_key: Optional[str] = None,
                      max_attempts: int = 1, correlation_id: str = "",
                      prepare_payload: Optional[Callable[[Any, str], tuple[Mapping[str, Any], str]]] = None
                      ) -> tuple[Job, bool]:
        """Publish ownership and ready work in the same existing queue transaction."""
        if max_attempts < 1 or not actor_id or not tenant_id or not request_hash:
            raise ValueError("owned jobs require an owner, request hash and positive max_attempts")
        now = self.clock()
        jid = f"job_{uuid.uuid4().hex}"
        with self.db.tx() as c:
            for key in dict.fromkeys(k for k in (idempotency_key, legacy_key) if k):
                prior = c.execute("SELECT * FROM jobs WHERE idempotency_key=?", (key,)).fetchone()
                if prior is not None:
                    if (prior["actor_id"] != actor_id or prior["tenant_id"] != tenant_id
                            or prior["kind"] != kind or prior["request_hash"] != request_hash
                            or prior["project_id"] != project_id or not prior["execution_id"]):
                        raise OwnedJobConflict("idempotency owner or request body mismatch")
                    return self._job(prior), True
            if prepare_payload is not None:
                payload, execution_id = prepare_payload(c, jid)
            c.execute(
                "INSERT INTO jobs (job_id,kind,status,payload,max_attempts,run_after,correlation_id,"
                "idempotency_key,created_at,updated_at,actor_id,tenant_id,project_id,execution_id,"
                "timeout_s,request_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (jid, kind, "queued", json.dumps(dict(payload), sort_keys=True), max_attempts, now,
                 correlation_id, idempotency_key, now, now, actor_id, tenant_id, project_id,
                 execution_id or jid, float(timeout_s), request_hash))
            row = c.execute("SELECT * FROM jobs WHERE job_id=?", (jid,)).fetchone()
            return self._job(row), False

    def claim(self, worker_id: str, *, kinds: Optional[Sequence[str]] = None,
              lease_s: float = 60.0) -> Optional[Job]:
        now = self.clock()
        kind_sql, kind_args = "", ()
        if kinds:
            kind_sql = f" AND kind IN ({','.join('?' * len(kinds))})"
            kind_args = tuple(kinds)
        with self.db.tx() as c:
            row = c.execute(
                "SELECT job_id FROM jobs WHERE ((status='queued' AND run_after<=?)"
                " OR (status='running' AND lease_expires_at<?))" + kind_sql +
                " ORDER BY run_after, created_at LIMIT 1", (now, now, *kind_args)).fetchone()
            if row is None:
                return None
            c.execute("UPDATE jobs SET status='running', lease_owner=?, lease_expires_at=?,"
                      " attempts=attempts+1, updated_at=? WHERE job_id=?",
                      (worker_id, now + lease_s, now, row["job_id"]))
        return self.get(row["job_id"])

    def _owned(self, c: Any, job_id: str, worker_id: str) -> None:
        r = c.execute("SELECT status, lease_owner FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if r is None or r["status"] != "running" or r["lease_owner"] != worker_id:
            raise LeaseLost(job_id)

    def heartbeat(self, job_id: str, worker_id: str, *, lease_s: float = 60.0,
                  progress: Optional[float] = None) -> bool:
        now = self.clock()
        try:
            with self.db.tx() as c:
                self._owned(c, job_id, worker_id)
                if progress is None:
                    c.execute("UPDATE jobs SET lease_expires_at=?, updated_at=? WHERE job_id=?",
                              (now + lease_s, now, job_id))
                else:
                    c.execute("UPDATE jobs SET lease_expires_at=?, progress=?, updated_at=? WHERE job_id=?",
                              (now + lease_s, max(0.0, min(1.0, progress)), now, job_id))
        except LeaseLost:
            return False
        return True

    def complete(self, job_id: str, worker_id: str,
                 result: Optional[Mapping[str, Any]] = None) -> Job:
        with self.db.tx() as c:
            self._owned(c, job_id, worker_id)
            c.execute("UPDATE jobs SET status='succeeded', progress=1, result=?, lease_owner='',"
                      " updated_at=? WHERE job_id=?",
                      (json.dumps(dict(result or {}), sort_keys=True), self.clock(), job_id))
        return self.get(job_id)  # type: ignore[return-value]

    def fail(self, job_id: str, worker_id: str, error: str, *,
             retry_delay_s: float = 5.0) -> Job:
        now = self.clock()
        with self.db.tx() as c:
            self._owned(c, job_id, worker_id)
            r = c.execute("SELECT attempts, max_attempts FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if r["attempts"] >= r["max_attempts"]:
                c.execute("UPDATE jobs SET status='dead', error=?, lease_owner='', updated_at=?"
                          " WHERE job_id=?", (error[:4000], now, job_id))
            else:
                backoff = retry_delay_s * (2 ** (r["attempts"] - 1))
                c.execute("UPDATE jobs SET status='queued', error=?, lease_owner='', run_after=?,"
                          " updated_at=? WHERE job_id=?", (error[:4000], now + backoff, now, job_id))
        return self.get(job_id)  # type: ignore[return-value]

    def cancel(self, job_id: str) -> bool:
        with self.db.tx() as c:
            return c.execute("UPDATE jobs SET status='cancelled', lease_owner='', updated_at=?"
                             " WHERE job_id=? AND status IN ('queued','running')",
                             (self.clock(), job_id)).rowcount > 0

    def counts(self) -> dict[str, int]:
        return {r[0]: r[1] for r in self.db.query("SELECT status, COUNT(*) FROM jobs GROUP BY status")}


class BuildContext:
    """Handed to a build executor.  Lets it report progress/logs safely."""

    def __init__(self, runner: "BuildJobRunner", job: Job, build_id: str) -> None:
        self._runner, self.job, self.build_id = runner, job, build_id

    @property
    def payload(self) -> Mapping[str, Any]:
        return self.job.payload

    def progress(self, fraction: float, message: str = "") -> None:
        if not self._runner.queue.heartbeat(self.job.job_id, self._runner.worker_id,
                                            lease_s=self._runner.lease_s, progress=fraction):
            raise LeaseLost(self.job.job_id)
        self._runner._emit("build.progress", self.job, self.build_id,
                           {"progress": max(0.0, min(1.0, fraction)), "message": message})

    def log(self, line: str, level: str = "info") -> None:
        self._runner._emit("build.log", self.job, self.build_id,
                           {"line": line[:2000], "level": level})


BuildExecutor = Callable[[BuildContext], Mapping[str, Any]]


class BuildService:
    """Submit builds: creates the build row and enqueues its job."""

    def __init__(self, builds: BuildRepository, queue: SqliteJobQueue) -> None:
        self.builds, self.queue = builds, queue

    def submit(self, project_id: str, *, target: str = "", options: Optional[Mapping[str, Any]] = None,
               correlation_id: str = "", idempotency_key: Optional[str] = None,
               max_attempts: int = 2) -> Build:
        build = self.builds.create_build(project_id, target)
        job = self.queue.enqueue(BUILD_JOB_KIND, {"build_id": build.build_id, "project_id": project_id,
                                                   "target": target, "options": dict(options or {})},
                                 max_attempts=max_attempts, correlation_id=correlation_id,
                                 idempotency_key=idempotency_key)
        return self.builds.set_status(build.build_id, "queued", job_id=job.job_id)

    def cancel(self, build_id: str) -> bool:
        b = self.builds.get_build(build_id)
        if not b or not b.job_id or not self.queue.cancel(b.job_id):
            return False
        self.builds.set_status(build_id, "cancelled")
        return True


class BuildJobRunner:
    """Worker loop for ``game.build`` jobs.  Emits envelope-v1 build events."""

    def __init__(self, queue: SqliteJobQueue, builds: BuildRepository, executor: BuildExecutor, *,
                 worker_id: Optional[str] = None, publisher: Optional[JobEventPublisher] = None,
                 lease_s: float = 120.0, retry_delay_s: float = 5.0) -> None:
        self.queue, self.builds, self.executor = queue, builds, executor
        self.worker_id = worker_id or f"wrk_{uuid.uuid4().hex[:12]}"
        self.publisher: JobEventPublisher = publisher or NullJobEventPublisher()
        self.lease_s, self.retry_delay_s = lease_s, retry_delay_s

    def _emit(self, type_: str, job: Job, build_id: str, payload: Mapping[str, Any]) -> None:
        env = make_envelope("build", type_, {"build_id": build_id, **payload},
                            correlation_id=job.correlation_id, job_id=job.job_id)
        try:
            self.publisher.publish(env)
        except Exception:  # pragma: no cover - sinks must never break builds
            pass

    def run_once(self) -> Optional[Job]:
        job = self.queue.claim(self.worker_id, kinds=[BUILD_JOB_KIND], lease_s=self.lease_s)
        if job is None:
            return None
        build_id = str(job.payload.get("build_id", ""))
        self.builds.set_status(build_id, "running")
        self._emit("build.started", job, build_id, {"attempt": job.attempts,
                                                    "target": job.payload.get("target", "")})
        try:
            result = dict(self.executor(BuildContext(self, job, build_id)) or {})
        except LeaseLost:
            return self.queue.get(job.job_id)
        except Exception as exc:  # executor failure
            err = safe_exception_text(exc)
            done = self.queue.fail(job.job_id, self.worker_id, err, retry_delay_s=self.retry_delay_s)
            final = done.status == "dead"
            self.builds.set_status(build_id, "failed" if final else "queued", error=err)
            self._emit("build.failed", job, build_id,
                       {"error": err, "attempt": job.attempts, "will_retry": not final})
            return done
        done = self.queue.complete(job.job_id, self.worker_id, result)
        self.builds.set_status(build_id, "succeeded", result=result)
        self._emit("build.completed", job, build_id, {"result": result})
        return done

    def drain(self, max_jobs: int = 100) -> int:
        n = 0
        while n < max_jobs and self.run_once() is not None:
            n += 1
        return n


class AgentEventEmitter:
    """Optional helper for agent runs to emit agent.* envelopes on the same sink."""

    def __init__(self, publisher: Optional[JobEventPublisher] = None) -> None:
        self.publisher: JobEventPublisher = publisher or NullJobEventPublisher()

    def _emit(self, type_: str, payload: Mapping[str, Any], correlation_id: str, job_id: str) -> None:
        self.publisher.publish(make_envelope("agent", type_, payload,
                                             correlation_id=correlation_id, job_id=job_id))

    def started(self, agent: str, *, correlation_id: str = "", job_id: str = "") -> None:
        self._emit("agent.started", {"agent": agent}, correlation_id, job_id)

    def step(self, agent: str, step: str, detail: Optional[Mapping[str, Any]] = None, *,
             correlation_id: str = "", job_id: str = "") -> None:
        self._emit("agent.step", {"agent": agent, "step": step, **dict(detail or {})}, correlation_id, job_id)

    def completed(self, agent: str, outcome: str = "ok", *, correlation_id: str = "", job_id: str = "") -> None:
        self._emit("agent.completed", {"agent": agent, "outcome": outcome}, correlation_id, job_id)
