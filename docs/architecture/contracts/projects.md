# Projects resource contract

**Status: contract only. These routes are not mounted.**

Typed schema: `skeleton/contracts/projects.py`
JSON schema: `docs/architecture/contracts/projects.schema.json`
Schema id: `skeleton.projects.v1`
Schema version: `1.0.0`

The app foundation client (`skeleton/client`, PR 4095) has auth, agents, and builds. Builds are engine executions. There is no Projects router on the engine or the backend, so this document is the alignment surface for a later `ProjectsClient` and for the app shell. Do not call these paths until handlers land under the same paths and schemas.

## Routes

| Method | Path | Idempotent | Body | Response |
|--------|------|------------|------|----------|
| POST | `/api/v1/projects` | No, unless `Idempotency-Key` is sent | `ProjectCreateRequest` | `Project` |
| GET | `/api/v1/projects` | Yes | Query: `actor_id`, `tenant_id`, optional `limit` (1–100, default 50), optional `cursor` | `ProjectList` |
| GET | `/api/v1/projects/{project_id}` | Yes | Query: `actor_id`, `tenant_id` | `Project` |
| POST | `/api/v1/projects/{project_id}/builds` | Yes, for the same `execution_id` | `ProjectBuildLinkRequest` | `ProjectBuildLink` |

Scope matches `BuildsClient`: `actor_id` and `tenant_id` are required. Identifiers are path-safe (`[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`). Timestamps are RFC3339 UTC ending in `Z`.

## Create from a brief

`POST /api/v1/projects` creates a `draft` project from a brief. The brief has a required `title` and optional `summary`, `genre`, and `constraints`. Unknown JSON fields are rejected (`PROJECT.INVALID`, HTTP 400).

A create without `Idempotency-Key` is not safe to retry. That matches the client gateway, which does not retry non-idempotent calls.

## List and get

`GET /api/v1/projects` returns `{schema_version, items, next_cursor}`. `next_cursor` is null on the last page.

`GET /api/v1/projects/{project_id}` returns one `Project`. A missing or out-of-scope project is `PROJECT.NOT_FOUND` (HTTP 404). The response must not say which of those two cases it was.

## Link to builds

A build is an engine execution. Its id is `execution_id`, the same id `BuildsClient` uses for `/api/v1/engine/executions/{execution_id}`.

`POST /api/v1/projects/{project_id}/builds` links an existing execution. It does not submit one. Submit stays `POST /api/v1/engine/executions`.

The project stores `build_ids` in link order, unique, at most 64. The first link moves a `draft` project to `active`. A second link of the same `execution_id` returns the same association with `replayed: true` and does not append again. A conflicting link (for example an execution owned by another tenant) is `PROJECT.BUILD_CONFLICT` (HTTP 409).

`GET` on the project is how a client reads the current `build_ids`. There is no separate list-builds route in v1.

## Errors

Errors use the Skeleton API envelope from `skeleton/api/errors.py`:

```json
{"error": {"type": "ProjectContractError", "code": "PROJECT.INVALID", "message": "title must be non-empty", "context": {}}}
```

| Code | HTTP | When |
|------|------|------|
| `PROJECT.INVALID` | 400 | Schema, version, or field rejection |
| `PROJECT.NOT_FOUND` | 404 | Unknown project, or project outside actor/tenant scope |
| `PROJECT.BUILD_CONFLICT` | 409 | Execution cannot be linked |

Context must not contain secret values. Configuration snapshots that might sit beside this API go through `skeleton/config/public_snapshot.py`.

## Internal handoff

`brief_digest()` is sha256 of the canonical brief JSON. Kernel, agents, memory, and the GameForge facade may store that digest. They do not import this module's HTTP routes, and this contract does not describe GameForge pipeline stages.

## What is intentionally absent

No handler, persistence, or `ProjectsClient` ships with this contract. Mounting the routes, storing projects, and checking that an `execution_id` belongs to the tenant are follow-on work and must consume this schema rather than invent a second one.
