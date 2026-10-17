"""Public job-queue API (stable import surface).  See docs/contracts/job_queue.md.

    from skeleton.app_services import job_api
    job_api.register_handler("game.build", fn)          # fn(ctx, payload) -> dict
    h = job_api.enqueue("game.build", {...}, actor_id=..., tenant_id=...)
    job_api.get_status(h.job_id); job_api.get_result(h.job_id); job_api.cancel(h.job_id)
    job_api.start_worker()                               # explicit/lazy; never from lifespan

Persistence: ``jobs`` table in skeleton.persistence.app_foundation (migration v7).
Long-run safety: the lease (visibility timeout) is max(visibility_timeout_s,
timeout_s + grace) and every ctx.progress/log/heartbeat extends it, so a 9-minute
job is never reclaimed as stale.  A job past ``timeout_s`` fails with code
``timeout`` on its next ctx call.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Optional

from skeleton.app_services.events import JobEventPublisher, NullJobEventPublisher, make_envelope
from skeleton.app_services.jobs import LeaseLost, SqliteJobQueue
from skeleton.observability.redaction import safe_exception_text
from skeleton.persistence.app_foundation.db import Database
from skeleton.persistence.app_foundation.repositories import SqliteBuildRepository

_log = logging.getLogger(__name__)

JobStatusName = Literal["pending", "queued", "running", "succeeded", "failed", "cancelled"]
DEFAULT_TIMEOUT_S = 900.0
LEASE_GRACE_S = 120.0
BUILD_KINDS_WITH_ROW = ("game.build",)


class IdempotencyMismatch(Exception):
    """Same idempotency key reused with a different request body."""


class JobTimeout(Exception):
    pass


@dataclass(frozen=True)
class JobHandle:
    job_id: str
    execution_id: str
    status: JobStatusName
    replayed: bool = False


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    status: JobStatusName
    progress: float
    message: str
    started_at: Optional[float]
    updated_at: float
    attempts: int


@dataclass(frozen=True)
class JobResult:
    status: JobStatusName
    result: Optional[dict]
    error: Optional[dict]  # {"code": str, "message": str}


def request_hash(kind: str, payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps({"kind": kind, "payload": payload}, sort_keys=True,
                                     separators=(",", ":"), default=str).encode()).hexdigest()


def _status_name(raw: str) -> JobStatusName:
    return {"dead": "failed"}.get(raw, raw)  # type: ignore[return-value]


class JobContext:
    """Passed to handlers. progress()/log()/heartbeat() extend the lease and emit build.* events."""

    def __init__(self, svc: "JobService", row: Mapping[str, Any], worker_id: str, lease_s: float) -> None:
        self._svc, self._worker, self._lease = svc, worker_id, lease_s
        self.job_id: str = row["job_id"]
        self.execution_id: str = row["execution_id"] or row["job_id"]
        self.kind: str = row["kind"]
        self.actor_id: str = row["actor_id"]
        self.tenant_id: str = row["tenant_id"]
        self.project_id: Optional[str] = row["project_id"]
        self.correlation_id: str = row["correlation_id"]
        self.timeout_s: float = float(row["timeout_s"])
        self._started = svc.clock()

    def heartbeat(self, progress: Optional[float] = None, message: Optional[str] = None) -> None:
        if self._svc.clock() - self._started > self.timeout_s:
            raise JobTimeout(f"job exceeded timeout_s={self.timeout_s:g}")
        if not self._svc.queue.heartbeat(self.job_id, self._worker, lease_s=self._lease, progress=progress):
            raise LeaseLost(self.job_id)
        if message is not None:
            with self._svc.db.tx() as c:
                c.execute("UPDATE jobs SET message=? WHERE job_id=?", (message[:500], self.job_id))

    def progress(self, fraction: float, message: str = "") -> None:
        f = max(0.0, min(1.0, float(fraction)))
        self.heartbeat(progress=f, message=message)
        self._svc._emit("build.progress", self, {"progress": f, "message": message})

    def log(self, line: str, level: str = "info") -> None:
        self.heartbeat()
        self._svc._emit("build.log", self, {"line": str(line)[:2000], "level": level})


Handler = Callable[[JobContext, dict], Mapping[str, Any]]


class JobService:
    def __init__(self, db: Database, *, publisher: Optional[JobEventPublisher] = None,
                 visibility_timeout_s: float = DEFAULT_TIMEOUT_S + LEASE_GRACE_S,
                 clock: Callable[[], float] = time.time) -> None:
        self.db, self.clock = db, clock
        self.queue = SqliteJobQueue(db, clock=clock)
        self.builds = SqliteBuildRepository(db)
        self.publisher: JobEventPublisher = publisher or NullJobEventPublisher()
        self.visibility_timeout_s = visibility_timeout_s
        self._handlers: dict[str, Handler] = {}

    # ---- registry -------------------------------------------------------
    def register_handler(self, kind: str, fn: Handler) -> None:
        if not kind or not callable(fn):
            raise ValueError("kind and callable handler required")
        self._handlers[kind] = fn

    def handler_kinds(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    # ---- producer -------------------------------------------------------
    def enqueue(self, kind: str, payload: Mapping[str, Any], *, actor_id: str, tenant_id: str,
                project_id: Optional[str] = None, idempotency_key: Optional[str] = None,
                correlation_id: Optional[str] = None, timeout_s: float = DEFAULT_TIMEOUT_S,
                max_attempts: int = 1) -> JobHandle:
        if not actor_id or not tenant_id:
            raise ValueError("actor_id and tenant_id are required")
        if not (0 < float(timeout_s) <= 6 * 3600):
            raise ValueError("timeout_s must be in (0, 21600]")
        payload = dict(payload)
        rhash = request_hash(kind, payload)
        scoped = f"{tenant_id}:{actor_id}:{kind}:{idempotency_key}" if idempotency_key else None
        if scoped:
            prior = self.db.query("SELECT * FROM jobs WHERE idempotency_key=?", (scoped,))
            if prior:
                r = prior[0]
                if r["request_hash"] and r["request_hash"] != rhash:
                    raise IdempotencyMismatch(idempotency_key)
                return JobHandle(r["job_id"], r["execution_id"] or r["job_id"], _status_name(r["status"]), True)
        execution_id = None
        if kind in BUILD_KINDS_WITH_ROW and project_id:
            build = self.builds.create_build(project_id, str(payload.get("target", "")))
            execution_id = build.build_id
            payload.setdefault("build_id", build.build_id)
        job = self.queue.enqueue(kind, payload, max_attempts=max_attempts,
                                 correlation_id=correlation_id or "", idempotency_key=scoped)
        execution_id = execution_id or job.job_id
        with self.db.tx() as c:
            c.execute("UPDATE jobs SET actor_id=?, tenant_id=?, project_id=?, execution_id=?, timeout_s=?,"
                      " request_hash=? WHERE job_id=?",
                      (actor_id, tenant_id, project_id, execution_id, float(timeout_s), rhash, job.job_id))
        if execution_id != job.job_id:
            self.builds.set_status(execution_id, "queued", job_id=job.job_id)
        return JobHandle(job.job_id, execution_id, "queued", False)

    def _row(self, job_id: str):
        rows = self.db.query("SELECT * FROM jobs WHERE job_id=?", (job_id,))
        if not rows:
            raise KeyError(job_id)
        return rows[0]

    def get_status(self, job_id: str) -> JobStatus:
        r = self._row(job_id)
        status = _status_name(r["status"])
        if status == "queued" and r["run_after"] > self.clock():
            status = "pending"
        return JobStatus(r["job_id"], status, float(r["progress"]), r["message"], r["started_at"],
                         float(r["updated_at"]), int(r["attempts"]))

    def get_result(self, job_id: str) -> JobResult:
        r = self._row(job_id)
        status = _status_name(r["status"])
        if status == "succeeded":
            return JobResult(status, json.loads(r["result"] or "{}"), None)
        if status in ("failed", "cancelled"):
            code = r["error_code"] or ("cancelled" if status == "cancelled" else "handler_error")
            return JobResult(status, None, {"code": code, "message": r["error"] or code})
        return JobResult(status, None, None)

    def cancel(self, job_id: str) -> bool:
        r = self._row(job_id)
        ok = self.queue.cancel(job_id)
        if ok and r["execution_id"] and r["execution_id"] != job_id:
            self.builds.set_status(r["execution_id"], "cancelled")
        return ok

    def get_by_execution(self, execution_id: str) -> Optional[str]:
        rows = self.db.query("SELECT job_id FROM jobs WHERE execution_id=?", (execution_id,))
        return rows[0]["job_id"] if rows else None

    # ---- consumer -------------------------------------------------------
    def _emit(self, type_: str, ctx: JobContext, payload: Mapping[str, Any]) -> None:
        try:
            self.publisher.publish(make_envelope(
                "build", type_, {"build_id": ctx.execution_id, "execution_id": ctx.execution_id,
                                 "kind": ctx.kind, **payload},
                correlation_id=ctx.correlation_id, job_id=ctx.job_id))
        except Exception:  # sinks never break jobs
            _log.debug("job event sink failed", exc_info=True)

    def _sync_build(self, r, status: str, **kw) -> None:
        if r["execution_id"] and r["execution_id"] != r["job_id"]:
            try:
                self.builds.set_status(r["execution_id"], status, **kw)
            except KeyError:
                pass

    def run_once(self, worker_id: str) -> Optional[str]:
        kinds = list(self._handlers)
        if not kinds:
            return None
        # Lease must outlive the whole job even without heartbeats.
        probe = self.db.query("SELECT MAX(timeout_s) FROM jobs WHERE status IN ('queued','running')")
        max_timeout = float(probe[0][0] or DEFAULT_TIMEOUT_S)
        lease = max(self.visibility_timeout_s, max_timeout + LEASE_GRACE_S)
        job = self.queue.claim(worker_id, kinds=kinds, lease_s=lease)
        if job is None:
            return None
        now = self.clock()
        with self.db.tx() as c:
            c.execute("UPDATE jobs SET started_at=COALESCE(started_at, ?) WHERE job_id=?", (now, job.job_id))
        r = self._row(job.job_id)
        ctx = JobContext(self, r, worker_id, lease)
        self._sync_build(r, "running")
        self._emit("build.started", ctx, {"attempt": job.attempts})
        try:
            result = dict(self._handlers[job.kind](ctx, dict(job.payload)) or {})
        except LeaseLost:
            return job.job_id
        except JobTimeout as exc:
            self._finish_failed(job.job_id, worker_id, r, ctx, "timeout", str(exc))
            return job.job_id
        except Exception as exc:
            self._finish_failed(job.job_id, worker_id, r, ctx, "handler_error", safe_exception_text(exc))
            return job.job_id
        try:
            self.queue.complete(job.job_id, worker_id, result)
        except LeaseLost:
            return job.job_id
        self._sync_build(r, "succeeded", result=result)
        self._emit("build.completed", ctx, {"result": result})
        return job.job_id

    def _finish_failed(self, job_id, worker_id, r, ctx, code, message) -> None:
        try:
            done = self.queue.fail(job_id, worker_id, message, retry_delay_s=5.0)
        except LeaseLost:
            return
        final = done.status == "dead"
        with self.db.tx() as c:
            c.execute("UPDATE jobs SET error_code=? WHERE job_id=?", (code, job_id))
        self._sync_build(r, "failed" if final else "queued", error=message)
        self._emit("build.failed", ctx, {"error": {"code": code, "message": message}, "will_retry": not final})


class JobWorker:
    """Background worker thread. Start explicitly (``start_worker()``), never from lifespan."""

    def __init__(self, svc: JobService, *, worker_id: Optional[str] = None, poll_s: float = 1.0) -> None:
        self.svc, self.poll_s = svc, poll_s
        self.worker_id = worker_id or f"wrk_{uuid.uuid4().hex[:12]}"
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "JobWorker":
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name=f"job-worker-{self.worker_id}", daemon=True)
            self._thread.start()
        return self

    def stop(self, timeout: Optional[float] = None) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def drain(self, max_jobs: int = 100) -> int:
        n = 0
        while n < max_jobs and self.svc.run_once(self.worker_id) is not None:
            n += 1
        return n

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self.svc.run_once(self.worker_id) is None:
                    self._stop.wait(self.poll_s)
            except Exception:
                _log.exception("job worker iteration failed")
                self._stop.wait(self.poll_s)


# ---- process-wide default (lazy) ----------------------------------------
_lock = threading.Lock()
_service: Optional[JobService] = None
_worker: Optional[JobWorker] = None


def get_job_service() -> JobService:
    global _service
    with _lock:
        if _service is None:
            from skeleton.app_services.runtime import get_app_services
            _service = get_app_services().jobs
        return _service


def set_job_service(svc: Optional[JobService]) -> None:
    """Test/composition hook."""
    global _service, _worker
    with _lock:
        if _worker is not None:
            _worker.stop(0)
        _service, _worker = svc, None


def register_handler(kind: str, fn: Handler) -> None:
    get_job_service().register_handler(kind, fn)


def enqueue(kind: str, payload: Mapping[str, Any], *, actor_id: str, tenant_id: str,
            project_id: Optional[str] = None, idempotency_key: Optional[str] = None,
            correlation_id: Optional[str] = None, timeout_s: float = DEFAULT_TIMEOUT_S) -> JobHandle:
    return get_job_service().enqueue(kind, payload, actor_id=actor_id, tenant_id=tenant_id,
                                     project_id=project_id, idempotency_key=idempotency_key,
                                     correlation_id=correlation_id, timeout_s=timeout_s)


def get_status(job_id: str) -> JobStatus:
    return get_job_service().get_status(job_id)


def get_result(job_id: str) -> JobResult:
    return get_job_service().get_result(job_id)


def cancel(job_id: str) -> bool:
    return get_job_service().cancel(job_id)


def start_worker(*, poll_s: float = 1.0) -> JobWorker:
    """Start (idempotently) the process-wide background worker thread."""
    global _worker
    svc = get_job_service()
    with _lock:
        if _worker is None:
            _worker = JobWorker(svc, poll_s=poll_s)
        return _worker.start()


__all__ = [
    "DEFAULT_TIMEOUT_S", "Handler", "IdempotencyMismatch", "JobContext", "JobHandle", "JobResult",
    "JobService", "JobStatus", "JobStatusName", "JobTimeout", "JobWorker", "cancel", "enqueue",
    "get_job_service", "get_result", "get_status", "register_handler", "request_hash",
    "set_job_service", "start_worker",
]
