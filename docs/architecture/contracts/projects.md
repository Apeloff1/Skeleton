# Projects resource contract

**Status: describes PR #4097.** The router is commit `959eec134`. #4097's current head is `c71ad467`, and `skeleton/api/projects_routes.py` is the same blob at both commits (`01e6121eaee7c4afc15e85a0c3772f9098e4c0fd`).

Typed schema: `skeleton/contracts/projects.py`
JSON schema: `docs/architecture/contracts/projects.schema.json`
Job queue: [`docs/contracts/job_queue.md`](../../contracts/job_queue.md)
Schema id: `skeleton.projects.v1`
Schema version: `1.0.0`

Handler: `skeleton/api/projects_routes.py`, mounted by `create_app` at `/api/v1/projects` behind `install_gate`. The domain map entry is `("/api/v1/projects", "projects")`. Store: `skeleton/persistence/app_foundation/projects_v1.py`.

## Auth

Every Projects call needs both:

- `x-gf-seal`, checked by `install_gate` before the handler
- `Authorization: Bearer <session>`

`actor_id` is the session user id. `tenant_id` is the process-wide `APP_TENANT_ID`, or `default` when that variable is unset. It is deployment-scoped until sessions carry a tenant. Neither value is taken from the query string. A body may repeat them, and the value must equal the session value. A different value is `PROJECT.INVALID`.

A missing or unknown bearer token is `PROJECT.UNAUTHENTICATED` (HTTP 401), message `valid session required`. A seal failure is the gate's own response, `401 invalid_seal` or `503 seal_unavailable`, and is not a `PROJECT.*` envelope.

A project is visible only for that actor and tenant. Anything else is `PROJECT.NOT_FOUND` (HTTP 404). The body does not say which of "missing" or "out of scope" it was.

## Routes

| Method | Path | Success | Replay | Body / query |
|--------|------|---------|--------|----------------|
| POST | `/api/v1/projects` | 201 `Project` | 200 `Project` | `brief`, optional `schema_version`, optional `actor_id` / `tenant_id`. Optional `Idempotency-Key` header, 1..128 characters. |
| GET | `/api/v1/projects` | 200 list | — | `limit` 1..100, default 50. `cursor` is `r:<rowid>` or omitted. |
| GET | `/api/v1/projects/{project_id}` | 200 `Project` | — | none |
| POST | `/api/v1/projects/{project_id}/builds` | 202 `Build` | 202 `Build` with `replayed: true` | Start fields below, or a link body. |
| GET | `/api/v1/projects/{project_id}/builds` | 200 list | — | `limit` and `cursor` as on the project list. Newest row first. |
| GET | `/api/v1/projects/{project_id}/builds/{build_id}` | 200 `Build` | — | none |

Unknown JSON fields are `PROJECT.INVALID`. `schema_version`, when sent, must be `1.0.0`.

## Project

```text
schema_version, project_id, actor_id, tenant_id, brief, status, build_ids, created_at, updated_at
```

`brief` on the resource is always the object `{title, summary, genre, constraints}`. `status` is `draft`, `active`, or `archived`. `build_ids` is the link order, unique, at most 64. `created_at` and `updated_at` are RFC3339 UTC ending in `Z`.

`POST` accepts `brief` as that object or as a plain string. A string is stored as `title` = first line, cut at 200 characters, and `summary` = the remaining lines, cut at 8000. `genre` is `""` and `constraints` is `[]`. An empty string is `PROJECT.INVALID`. The project name is `brief.title`. The same actor and the same title is `PROJECT.NAME_CONFLICT` (HTTP 409).

`Idempotency-Key` is stored as `{tenant}:{actor}:{key}`. The same key and the same brief returns 200 and the original project. The same key and a different brief is `PROJECT.IDEMPOTENCY_MISMATCH` (HTTP 409). Equality is sha256 of the canonical brief JSON.

`GET /api/v1/projects` returns `{schema_version, items, next_cursor}` in row order. `next_cursor` is `r:<rowid>` when another page exists, otherwise null. `limit=0`, `limit=101`, and a non-numeric limit are `PROJECT.INVALID`. A cursor other than `r:<digits>` is `PROJECT.INVALID`.

The first build link moves a `draft` project to `active`.

## Build

A start is `POST` without `execution_id`:

| Field | Rule |
|-------|------|
| `target` | string, at most 64 characters, default `""` |
| `options` | object, default `{}` |
| `idempotency_key` | optional string, 1..128 characters |

The handler calls `job_api.enqueue("game.build", {"target", "options"}, ...)`. The `game.build` worker runs `build_playable_game` (#4119); this route does not call `Forge.materialise` itself. `x-request-id` is the correlation id. The effective idempotency key is `{tenant}:{actor}:game.build:{project_id}:{key}`. The same key with the same target and options returns 202 and the original build with `replayed: true`. A different target or options is `PROJECT.IDEMPOTENCY_MISMATCH`. See [`docs/contracts/job_queue.md`](../../contracts/job_queue.md).

`Build` is:

```text
schema_version, schema_id, build_id, execution_id, project_id, status,
target, job_id, result, error, created_at, updated_at, replayed
```

`schema_id` is `skeleton.projects.v1`. `execution_id` equals `build_id`. `status` is `pending`, `queued`, `running`, `succeeded`, `failed`, or `cancelled`. A start returns `queued` once the job is enqueued. `job_id` is a string or null. `result` is an object. `error` is a string. Timestamps are RFC3339 UTC ending in `Z`.

The new build id is appended to `build_ids`. A 65th link is `PROJECT.BUILD_CONFLICT` (HTTP 409) and the job just enqueued is cancelled. An `execution_id` already linked for another tenant is the same code.

A link is `POST` with `execution_id` and without `target`, `options`, or `idempotency_key`. Combining them is `PROJECT.INVALID`. The response is `ProjectBuildLink`:

```text
schema_version, project_id, execution_id, linked_at, replayed
```

The first link is HTTP 201. The same execution again is HTTP 200 with `replayed: true` and the original `linked_at`. `execution_id` must match `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`.

`GET .../builds` returns `{schema_version, items, next_cursor}` for build rows, newest first, at most `limit` per page. An execution that was only linked, and has no build row, is on `project.build_ids` and is not in this list. A missing build id is `PROJECT.NOT_FOUND`.

## Errors

```json
{"error": {"type": "ProjectContractError", "code": "PROJECT.NOT_FOUND", "message": "project not found", "context": {}}}
```

| Code | HTTP | When |
|------|------|------|
| `PROJECT.INVALID` | 400 | Body, brief, limit, cursor, version, or a session identity that does not match |
| `PROJECT.UNAUTHENTICATED` | 401 | Missing or unknown bearer session |
| `PROJECT.NOT_FOUND` | 404 | Project or build outside this actor and tenant |
| `PROJECT.NAME_CONFLICT` | 409 | This actor already has that title |
| `PROJECT.IDEMPOTENCY_MISMATCH` | 409 | Same key, different brief or different target/options |
| `PROJECT.BUILD_CONFLICT` | 409 | Build link refused (64-link cap, or execution owned by another tenant) |
| `PROJECT.UNAVAILABLE` | 503 | Storage failed. The message is `project storage unavailable` and the driver text is not returned. |

`context` is `{}` on these handler errors and must not carry secrets.
