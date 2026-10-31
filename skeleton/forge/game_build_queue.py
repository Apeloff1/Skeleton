"""Job-queue adapter for ``game.build``.

``POST /api/v1/game/build`` calls ``enqueue`` and returns 202. The handler is
``build_playable_game``. Progress goes through ``ctx.progress`` and
``ctx.heartbeat``.

The durable queue owner is ``skeleton.app_services.job_api`` (see
``docs/contracts/job_queue.md``). Every call delegates to that API when it is
available. An optional in-process fallback implements the same ``enqueue`` / ``JobHandle`` /
``JobContext`` surface, including one worker so a build cannot block the
request thread. Projects ``POST /builds`` already enqueues kind ``game.build``;
this handler accepts that payload and the product route payload.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

BUILD_KIND = "game.build"
DEFAULT_TIMEOUT_S = 900.0


class IdempotencyMismatch(Exception):
    """Same idempotency key reused with a different request body."""


class JobTimeout(Exception):
    pass


@dataclass(frozen=True)
class JobHandle:
    job_id: str
    execution_id: str
    status: str
    replayed: bool = False


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    status: str
    progress: float
    message: str
    started_at: Optional[float]
    updated_at: float
    attempts: int


@dataclass(frozen=True)
class JobResult:
    status: str
    result: Optional[dict]
    error: Optional[dict]


def request_hash(kind: str, payload: Mapping[str, Any]) -> str:
    body = json.dumps({"kind": kind, "payload": payload}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def _brief_from_job_payload(payload: Mapping[str, Any]) -> Any:
    if "brief" in payload:
        return payload["brief"]
    options = payload.get("options") if isinstance(payload.get("options"), Mapping) else {}
    if isinstance(options, Mapping) and "brief" in options:
        return options["brief"]
    title = str(options.get("title") or payload.get("target") or "playable game")
    structured: dict[str, Any] = {"title": title}
    if options.get("summary"):
        structured["summary"] = str(options["summary"])
    if options.get("genre"):
        structured["genre"] = str(options["genre"])
    constraints = options.get("constraints")
    if isinstance(constraints, list):
        structured["constraints"] = [str(item) for item in constraints]
    return structured


def _builder_deadline_s(body: Mapping[str, Any], options: Mapping[str, Any], ctx: Any) -> float:
    """The builder budget is the job ``timeout_s``, or a smaller payload deadline."""
    raw_timeout = getattr(ctx, "timeout_s", None)
    if raw_timeout is None:
        raw_timeout = DEFAULT_TIMEOUT_S
    try:
        timeout_s = float(raw_timeout)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_s must be a number of seconds") from exc
    raw = body.get("deadline_s", None)
    if raw is None:
        raw = options.get("deadline_s", None)
    if raw is None:
        return timeout_s
    if isinstance(raw, bool):
        raise ValueError("deadline_s must be a number of seconds")
    try:
        asked = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("deadline_s must be a number of seconds") from exc
    if asked < 0:
        raise ValueError("deadline_s must be a number of seconds")
    return min(asked, timeout_s)


def handle_game_build(ctx: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    """``game.build`` handler. Projects and ``/api/v1/game/build`` share it."""
    from skeleton.forge.game_builder import build_playable_game, public_payload

    ctx.progress(0.05, "compiling brief")
    ctx.heartbeat()
    body = dict(payload or {})
    options = body.get("options") if isinstance(body.get("options"), Mapping) else {}

    def on_progress(fraction: float, message: str) -> None:
        ctx.progress(0.1 + 0.85 * max(0.0, min(1.0, float(fraction))), message)
        ctx.heartbeat()

    deadline_s = _builder_deadline_s(body, options, ctx)
    playtest = body.get("playtest", options.get("playtest", "off"))
    rounds = body.get("max_rounds", options.get("max_rounds", 3))
    kwargs: dict[str, Any] = {
        "era": body.get("era") or options.get("era") or None,
        "repair_mode": str(body.get("repair_mode") or options.get("repair_mode") or "apply"),
        "playtest_mode": str(playtest or "off"),
        "max_rounds": int(rounds),
        "binary": body.get("binary") or options.get("binary"),
        "actor_id": getattr(ctx, "actor_id", None) or None,
        "tenant_id": getattr(ctx, "tenant_id", None) or None,
        "execution_id": getattr(ctx, "execution_id", None) or None,
        "project_id": getattr(ctx, "project_id", None) or None,
        "deadline_s": deadline_s,
        "on_progress": on_progress,
        "target": str(body.get("target") or options.get("target") or "godot"),
    }
    if "archetype" in body or "archetype" in options:
        kwargs["archetype"] = body.get("archetype", options.get("archetype")) or None
    result = build_playable_game(_brief_from_job_payload(body), **kwargs)
    try:
        ctx.progress(1.0, "complete" if result.get("ok") else "failed")
        ctx.heartbeat()
    except Exception as exc:
        # A finished build that lands on the timeout boundary still returns its
        # payload. A timeout raised earlier, inside on_progress, propagates.
        if type(exc).__name__ != "JobTimeout":
            raise
    include = bool(body.get("include_files") or options.get("include_files"))
    return public_payload(result, include_files=include)


class _FallbackContext:
    def __init__(self, service: "_FallbackQueue", row: dict[str, Any]) -> None:
        self._service = service
        self._row = row
        self.job_id = row["job_id"]
        self.execution_id = row["execution_id"]
        self.kind = row["kind"]
        self.actor_id = row["actor_id"]
        self.tenant_id = row["tenant_id"]
        self.project_id = row["project_id"]
        self.correlation_id = row["correlation_id"]
        self.timeout_s = float(row["timeout_s"])
        self._started = row["started_at"] or service.clock()

    def heartbeat(self, progress: Optional[float] = None, message: Optional[str] = None) -> None:
        if self._service.clock() - self._started > self.timeout_s:
            raise JobTimeout(f"job exceeded timeout_s={self.timeout_s:g}")
        self._service._touch(self.job_id, progress=progress, message=message)

    def progress(self, fraction: float, message: str = "") -> None:
        self.heartbeat(progress=max(0.0, min(1.0, float(fraction))), message=message)

    def log(self, line: str, level: str = "info") -> None:
        del level
        self.heartbeat(message=str(line)[:500])


class _FallbackQueue:
    """In-process stand-in for ``skeleton.app_services.job_api.JobService``."""

    def __init__(self) -> None:
        self.clock = time.time
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._by_execution: dict[str, str] = {}
        self._by_idempotency: dict[str, str] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._worker: Optional["_FallbackWorker"] = None

    def register_handler(self, kind: str, fn: Callable[..., Any]) -> None:
        if not kind or not callable(fn):
            raise ValueError("kind and callable handler required")
        self._handlers[kind] = fn

    def enqueue(
        self,
        kind: str,
        payload: Mapping[str, Any],
        *,
        actor_id: str,
        tenant_id: str,
        project_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        request_digest: Optional[str] = None,
    ) -> JobHandle:
        if not actor_id or not tenant_id:
            raise ValueError("actor_id and tenant_id are required")
        if not (0 < float(timeout_s) <= 6 * 3600):
            raise ValueError("timeout_s must be in (0, 21600]")
        if project_id:
            raise ValueError("project-linked jobs require the durable queue owner")
        if request_digest is not None and (not isinstance(request_digest, str) or len(request_digest) != 64
                or any(char not in "0123456789abcdef" for char in request_digest)):
            raise ValueError("request_digest must be a SHA-256 hex digest")
        body = dict(payload)
        digest = request_digest if request_digest is not None else request_hash(kind, body)
        scoped = ("owned:" + hashlib.sha256(json.dumps([tenant_id, actor_id, kind, idempotency_key],
                  separators=(",", ":")).encode()).hexdigest()) if idempotency_key else None
        now = self.clock()
        with self._lock:
            if scoped and scoped in self._by_idempotency:
                prior = self._jobs[self._by_idempotency[scoped]]
                if prior["request_hash"] != digest:
                    raise IdempotencyMismatch(idempotency_key or "")
                return JobHandle(prior["job_id"], prior["execution_id"], prior["status"], True)
            job_id = f"job_{uuid.uuid4().hex}"
            execution_id = f"exe_{uuid.uuid4().hex}" if project_id else job_id
            row = {
                "job_id": job_id,
                "execution_id": execution_id,
                "status": "queued",
                "kind": kind,
                "payload": body,
                "actor_id": actor_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "correlation_id": correlation_id or "",
                "timeout_s": float(timeout_s),
                "idempotency_key": scoped,
                "request_hash": digest,
                "progress": 0.0,
                "message": "",
                "started_at": None,
                "updated_at": now,
                "attempts": 0,
                "result": None,
                "error_code": None,
                "error": None,
                "run_after": now,
            }
            self._jobs[job_id] = row
            self._by_execution[execution_id] = job_id
            if scoped:
                self._by_idempotency[scoped] = job_id
        return JobHandle(job_id, execution_id, "queued", False)

    def _touch(self, job_id: str, *, progress: Optional[float] = None, message: Optional[str] = None) -> None:
        with self._lock:
            row = self._jobs.get(job_id)
            if row is None or row["status"] != "running":
                return
            row["updated_at"] = self.clock()
            if progress is not None:
                row["progress"] = float(progress)
            if message is not None:
                row["message"] = message[:500]

    def get_status(self, job_id: str) -> JobStatus:
        with self._lock:
            row = self._jobs.get(job_id)
            if row is None:
                raise KeyError(job_id)
            status = row["status"]
            if status == "queued" and row["run_after"] > self.clock():
                status = "pending"
            return JobStatus(
                row["job_id"], status, float(row["progress"]), row["message"],
                row["started_at"], float(row["updated_at"]), int(row["attempts"]),
            )

    def get_result(self, job_id: str) -> JobResult:
        with self._lock:
            row = self._jobs.get(job_id)
            if row is None:
                raise KeyError(job_id)
            status = row["status"]
            if status == "succeeded":
                return JobResult(status, dict(row["result"] or {}), None)
            if status in ("failed", "cancelled"):
                code = row["error_code"] or ("cancelled" if status == "cancelled" else "handler_error")
                return JobResult(status, None, {"code": code, "message": row["error"] or code})
            return JobResult(status, None, None)

    def get_by_execution(self, execution_id: str) -> Optional[str]:
        with self._lock:
            return self._by_execution.get(execution_id)

    def get_identity(self, job_id: str) -> dict[str, str]:
        with self._lock:
            row = self._jobs[job_id]
            return {key: row.get(key, "") for key in
                    ("job_id", "execution_id", "kind", "actor_id", "tenant_id")}

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            row = self._jobs.get(job_id)
            if row is None or row["status"] not in ("queued", "running"):
                return False
            row["status"] = "cancelled"
            row["error_code"] = "cancelled"
            row["error"] = "cancelled"
            row["updated_at"] = self.clock()
            return True

    def run_once(self) -> Optional[str]:
        with self._lock:
            kinds = set(self._handlers)
            now = self.clock()
            chosen = None
            for row in self._jobs.values():
                if row["status"] == "queued" and row["kind"] in kinds and row["run_after"] <= now:
                    chosen = row
                    break
            if chosen is None:
                return None
            chosen["status"] = "running"
            chosen["started_at"] = chosen["started_at"] or now
            chosen["attempts"] = int(chosen["attempts"]) + 1
            chosen["updated_at"] = now
            job_id = chosen["job_id"]
            kind = chosen["kind"]
            payload = dict(chosen["payload"])
            handler = self._handlers[kind]
            ctx = _FallbackContext(self, chosen)
        try:
            result = dict(handler(ctx, payload) or {})
        except JobTimeout as exc:
            self._finish_failed(job_id, "timeout", str(exc))
            return job_id
        except Exception as exc:
            self._finish_failed(job_id, "handler_error", str(exc)[:500])
            return job_id
        with self._lock:
            row = self._jobs[job_id]
            if row["status"] == "cancelled":
                return job_id
            row["status"] = "succeeded"
            row["result"] = result
            row["progress"] = 1.0
            row["updated_at"] = self.clock()
        return job_id

    def _finish_failed(self, job_id: str, code: str, message: str) -> None:
        with self._lock:
            row = self._jobs.get(job_id)
            if row is None or row["status"] == "cancelled":
                return
            row["status"] = "failed"
            row["error_code"] = code
            row["error"] = message
            row["updated_at"] = self.clock()

    def start_worker(self, *, poll_s: float = 0.05) -> "_FallbackWorker":
        with self._lock:
            if self._worker is None or not self._worker.running:
                self._worker = _FallbackWorker(self, poll_s=poll_s)
            worker = self._worker
        return worker.start()

    def drain(self, max_jobs: int = 100) -> int:
        count = 0
        while count < max_jobs and self.run_once() is not None:
            count += 1
        return count


class _FallbackWorker:
    def __init__(self, queue: _FallbackQueue, *, poll_s: float) -> None:
        self.queue = queue
        self.poll_s = poll_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "_FallbackWorker":
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="game-build-worker", daemon=True)
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
        return self.queue.drain(max_jobs)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self.queue.run_once() is None:
                    self._stop.wait(self.poll_s)
            except Exception:
                self._stop.wait(self.poll_s)


_lock = threading.Lock()
_fallback: Optional[_FallbackQueue] = None
_using_real = False


def _real_api():
    try:
        from skeleton.app_services import job_api
    except ImportError:
        return None
    return job_api


def _fallback_queue() -> _FallbackQueue:
    global _fallback
    with _lock:
        if _fallback is None:
            _fallback = _FallbackQueue()
        return _fallback


def _backend():
    global _using_real
    api = _real_api()
    if api is not None:
        _using_real = True
        return api
    _using_real = False
    return _fallback_queue()


def using_internal_systems_queue() -> bool:
    """True when the canonical durable job API is available."""
    _backend()
    return _using_real


def register_handler(kind: str, fn: Callable[..., Any]) -> None:
    _backend().register_handler(kind, fn)


def enqueue(kind: str, payload: Mapping[str, Any], *, actor_id: str, tenant_id: str,
            project_id: Optional[str] = None, idempotency_key: Optional[str] = None,
            correlation_id: Optional[str] = None, timeout_s: float = DEFAULT_TIMEOUT_S,
            request_digest: Optional[str] = None) -> JobHandle:
    try:
        handle = _backend().enqueue(
            kind, payload, actor_id=actor_id, tenant_id=tenant_id, project_id=project_id,
            idempotency_key=idempotency_key, correlation_id=correlation_id, timeout_s=timeout_s,
            request_digest=request_digest,
        )
    except Exception as exc:
        if exc.__class__.__name__ == "IdempotencyMismatch" and not isinstance(exc, IdempotencyMismatch):
            raise IdempotencyMismatch(str(exc)) from exc
        raise
    if not isinstance(handle, JobHandle):
        return JobHandle(handle.job_id, handle.execution_id, handle.status, bool(handle.replayed))
    return handle


def get_status(job_id: str) -> JobStatus:
    status = _backend().get_status(job_id)
    if isinstance(status, JobStatus):
        return status
    return JobStatus(
        status.job_id, status.status, float(status.progress), status.message,
        status.started_at, float(status.updated_at), int(status.attempts),
    )


def get_result(job_id: str) -> JobResult:
    result = _backend().get_result(job_id)
    if isinstance(result, JobResult):
        return result
    return JobResult(result.status, result.result, result.error)


def cancel(job_id: str) -> bool:
    return bool(_backend().cancel(job_id))


def start_worker(*, poll_s: float = 0.05):
    backend = _backend()
    if _using_real:
        return backend.start_worker()
    return backend.start_worker(poll_s=poll_s)


def drain(max_jobs: int = 100) -> int:
    backend = _backend()
    if _using_real:
        worker = backend.start_worker()
        return int(worker.drain(max_jobs))
    return _fallback_queue().drain(max_jobs)


def get_by_execution(execution_id: str) -> Optional[str]:
    backend = _backend()
    if _using_real:
        return backend.get_job_service().get_by_execution(execution_id)
    return _fallback_queue().get_by_execution(execution_id)


def enqueue_game_build(payload: Mapping[str, Any], **kwargs: Any) -> JobHandle:
    """Register the playable-game handler and enqueue kind ``game.build``."""
    register_handler(BUILD_KIND, handle_game_build)
    return enqueue(BUILD_KIND, payload, **kwargs)


def execution_view(execution_id: str, *, actor_id: Optional[str] = None,
                   tenant_id: Optional[str] = None) -> dict[str, Any]:
    """Status document for ``GET /api/v1/game/build/{execution_id}``."""
    from skeleton.forge.game_builder import RUN_SCHEMA

    job_id = get_by_execution(execution_id)
    if not job_id:
        raise KeyError(execution_id)
    if actor_id is not None or tenant_id is not None:
        backend = _backend()
        identity = backend.get_identity(job_id)
        if not isinstance(identity, Mapping):
            identity = vars(identity)
        if (not actor_id or not tenant_id or identity.get("actor_id") != actor_id
                or identity.get("tenant_id") != tenant_id or identity.get("kind") != BUILD_KIND
                or identity.get("execution_id") != execution_id):
            raise KeyError(execution_id)
    status = get_status(job_id)
    result = get_result(job_id)
    return {
        "schema_version": RUN_SCHEMA,
        "job_id": job_id,
        "execution_id": execution_id,
        "status": status.status,
        "progress": status.progress,
        "message": status.message,
        "attempts": status.attempts,
        "result": result.result,
        "error": result.error,
    }


__all__ = [
    "BUILD_KIND",
    "DEFAULT_TIMEOUT_S",
    "IdempotencyMismatch",
    "JobHandle",
    "JobResult",
    "JobStatus",
    "JobTimeout",
    "cancel",
    "drain",
    "enqueue",
    "enqueue_game_build",
    "execution_view",
    "get_by_execution",
    "get_result",
    "get_status",
    "handle_game_build",
    "register_handler",
    "start_worker",
    "using_internal_systems_queue",
]
