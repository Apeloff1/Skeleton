# Job queue public API (v1)

Module: `skeleton/app_services/job_api.py` (re-exported from `skeleton.app_services`).
Persistence: the `jobs` table in `skeleton.persistence.app_foundation` (migrations v3 and v7).
Owner: Internal Systems. Import only this module, never `skeleton.app_services.jobs` internals.

```python
from skeleton.app_services import job_api

def build_playable_game_handler(ctx: job_api.JobContext, payload: dict) -> dict:
    ctx.progress(0.1, "compiling")       # extends lease, emits build.progress
    ctx.log("linking rom")              # extends lease, emits build.log
    ctx.heartbeat()                     # extends lease only
    return {"rom_asset_id": "..."}      # JSON-serialisable result

job_api.register_handler("game.build", build_playable_game_handler)
# The production handler calls build_playable_game (#4119), the only
# build entry wrapping Forge.materialise / godot_emit.
job_api.start_worker()                  # explicit, idempotent; NOT from api/server.py lifespan
h = job_api.enqueue("game.build", {"target": "gb"}, actor_id=user, tenant_id=tenant,
                    project_id=pid, idempotency_key="k", correlation_id=request_id, timeout_s=900)
# HTTP layer returns 202 with h.job_id / h.execution_id
```

## Signatures

| Function | Returns |
|---|---|
| `enqueue(kind: str, payload: dict, *, actor_id: str, tenant_id: str, project_id: str \| None = None, idempotency_key: str \| None = None, correlation_id: str \| None = None, timeout_s: float = 900, request_digest: str \| None = None) -> JobHandle` | `JobHandle{job_id, execution_id, status, replayed}` |
| `get_status(job_id) -> JobStatus` | `JobStatus{job_id, status, progress: 0..1, message, started_at: float \| None, updated_at: float, attempts}` (epoch seconds) |
| `get_result(job_id) -> JobResult` | `JobResult{status, result: dict \| None, error: {code, message} \| None}` |
| `get_identity(job_id) -> JobIdentity` | Durable `JobIdentity{job_id, execution_id, kind, actor_id, tenant_id}`; HTTP adapters must check the exact actor, tenant, kind and execution before reading status/results |
| `cancel(job_id) -> bool` | True if it was queued or running |
| `register_handler(kind, fn(ctx, payload) -> dict)` | Registers the handler on the process-wide service |
| `start_worker(*, poll_s=1.0) -> JobWorker` | Starts a daemon thread (idempotent). `JobWorker.stop()` stops it, and `drain()` runs jobs synchronously |
| `get_job_service()` / `set_job_service(svc)` | Lazy process-wide `JobService`, plus a composition/test hook |

`status` is one of `pending | queued | running | succeeded | failed | cancelled`. `pending` means queued with a future `run_after` (retry backoff). Unknown `job_id` raises `KeyError`.

`JobContext` attributes: `job_id, execution_id, kind, actor_id, tenant_id, project_id, correlation_id, timeout_s`.

## Semantics

- **execution_id**: for `kind="game.build"` with a `project_id`, a `builds` row is created and `execution_id == build_id`, the id the Projects API exposes. Its status and result are kept in sync. For other kinds, `execution_id == job_id`.
- **Idempotency**: the key is a SHA-256 digest of the JSON array `[tenant_id, actor_id, kind, idempotency_key]`, prefixed `owned:` so identifiers containing colons remain distinct. Re-enqueueing with an identical `payload` and project binding returns the original handle with `replayed=True`. A different payload raises `IdempotencyMismatch`; the Projects API maps that to 409 `PROJECT.IDEMPOTENCY_MISMATCH`. Equality is a sha256 of the canonical JSON `{kind, payload}`. Legacy colon-scoped keys replay only when the persisted exact actor, tenant, kind, project, execution identity and request hash establish the same binding; unowned or unbound rows fail closed.
- **Ownership**: the ready queue row and its actor, tenant, execution identity, timeout and request hash are committed in one transaction before a worker can claim it. Project-linked public jobs require an existing project owned by that actor and tenant. Trusted internal status/result calls remain available; HTTP adapters enforce ownership through `get_identity` first, including after restart.
- **HTTP request binding**: an adapter can supply `request_digest`, the SHA-256 of its full submitted request, while passing a normalized worker payload. `/api/v1/game/build` binds the complete submitted JSON this way; explicit defaults and ignored fields cannot change under an existing key. Project build creation and its initial job link participate in the queue transaction after the idempotency check, preventing orphan builds or a producer status write after a fast worker finishes.
- **Long jobs and leases**: a claimed job is leased for `max(visibility_timeout_s, timeout_s + 120)` seconds. The default visibility is 1020 s, which covers 900 s builds. Every `ctx.progress/log/heartbeat` extends the lease, so a ~9 minute job is never reclaimed as stale. A worker that dies stops heartbeating, and its job becomes claimable again once the lease expires (at-least-once delivery).
- **Timeout**: when the handler calls ctx after `timeout_s` has elapsed, it gets `JobTimeout` and the job fails with `error.code = "timeout"`.
- **Failures**: a handler exception fails the job with `error.code = "handler_error"`; the message is redacted by `safe_exception_text`. `max_attempts` defaults to 1 for the public API, so there are no automatic retries. Cancelled jobs report `error.code = "cancelled"`.
- **Events**: `build.started`, `build.progress`, `build.log`, `build.completed` and `build.failed` go out as envelope v1 on the AppServices `FanOutPublisher` (Walt's hub subscribes there). The payload always carries `build_id` (= execution_id), `execution_id` and `kind`; secrets are redacted.
- **Workers**: only kinds with a registered handler are claimed. A `game.build` enqueued before #4119 registers its handler stays `queued`.
