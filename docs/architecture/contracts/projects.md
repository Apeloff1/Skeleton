# Projects resource contract

**Status: describes the #4097 Projects router at its `/api/v1/projects` mount.**

Typed schema: `skeleton/contracts/projects.py`
JSON schema: `docs/architecture/contracts/projects.schema.json`
Schema id: `skeleton.projects.v1`
Schema version: `1.1.0`

Checked implementation: PR [#4097](https://github.com/Apeloff1/Skeleton/pull/4097), branch `is/app-foundation-persistence`, commit `7065e555f9fff380a85ae479a79d3c34966ca097`, module `skeleton/app_services/projects_api.py`.

That commit still registers prefix `/api/app/projects` and returns FastAPI `{"detail": ...}` bodies. Internal Systems is moving the same router to `/api/v1/projects` inside `create_app`, behind `install_gate`. This document is that moved contract. It is not a second resource.

## Auth

`Authorization: Bearer <session token>`. The handler resolves the session and derives the caller.

| Session fact | Where it goes |
|--------------|----------------|
| user id (`SessionPrincipal.user_id`) | `Project.owner_id`. This is the actor. |
| tenant, when the session has one | server-side scope only. The project row has no tenant column. |

`actor_id` and `tenant_id` are not request fields. A body that includes them is `PROJECT.INVALID`. A missing or unknown bearer token is `PROJECT.UNAUTHENTICATED` (HTTP 401). `install_gate` still runs in front of the router.

A project is visible when `owner_id` equals the session user. Another user's project is `PROJECT.NOT_FOUND` (HTTP 404). The response does not say whether the id is missing or owned by someone else.

## Routes

| Method | Path | Status | Body | Response |
|--------|------|--------|------|----------|
| POST | `/api/v1/projects` | 201 | `ProjectCreateRequest` | `Project` |
| GET | `/api/v1/projects` | 200 | none | `{"projects": [Project]}` |
| GET | `/api/v1/projects/{project_id}` | 200 | none | `Project` |
| POST | `/api/v1/projects/{project_id}/builds` | 202 | `BuildCreateRequest` | `Build` |
| GET | `/api/v1/projects/{project_id}/builds` | 200 | none | `{"builds": [Build]}` |
| GET | `/api/v1/projects/{project_id}/builds/{build_id}` | 200 | none | `Build` |

`x-request-id`, when sent on create-build, is stored as the job correlation id.

## Project

`Project` is the checked `ProjectOut`:

`project_id`, `owner_id`, `name`, `brief`, `settings`, `created_at`, `updated_at`

`created_at` and `updated_at` are epoch seconds. `settings` is a JSON object and defaults to `{}`.

### Create

`brief` is required and is either:

- a string of 1 to 20000 characters, the form the checked `ProjectCreate` model accepts, or
- an object with required `title` and optional `summary`, `genre`, and `constraints`

Both forms are stored and returned as sent. A structured brief is not collapsed to a string.

`name` is optional. When it is missing or blank, a string brief uses the first line, cut at 80 characters, or `Untitled project`. A structured brief uses `title`. An explicit name is stripped and may be up to 200 characters.

The same owner and the same name is `PROJECT.CONFLICT` (HTTP 409), the checked unique-name failure.

## Build

`Build` is the checked `BuildOut` plus `execution_id`:

`build_id`, `project_id`, `status`, `target`, `job_id`, `result`, `error`, `created_at`, `updated_at`, `execution_id`

`status` is one of `pending`, `queued`, `running`, `succeeded`, `failed`, `cancelled`. `job_id` is a string or null. `result` is an object. `error` is a string. Timestamps are epoch seconds.

`execution_id` is the engine execution this build started or linked. It is the same identifier `BuildsClient` uses for `/api/v1/engine/executions/{execution_id}`. The checked `BuildOut` does not yet include this field; the move adds it so the 202 body returns the execution.

### Start

`POST /api/v1/projects/{project_id}/builds` without `execution_id` starts a build. That is `BuildService.submit`: create the build row, enqueue a `game.build` job, set status to `queued`, and return the Build with `job_id` and `execution_id` set. HTTP 202.

Body fields, all optional:

| Field | Rule |
|-------|------|
| `target` | string, at most 64 characters, default `""` |
| `options` | object, default `{}` |
| `idempotency_key` | string, 1 to 128 characters |

The router scopes the key as `{project_id}:{idempotency_key}`. A repeat with the same key resolves to the original job: the response `job_id` equals the first response's `job_id`.

### Link

Sending `execution_id` links that execution and does not enqueue a job. The response Build carries that `execution_id`, `job_id: null`, and status `pending`. `target`, `options`, and `idempotency_key` are not a second submit on this path. An execution the session cannot attach is `PROJECT.BUILD_CONFLICT` (HTTP 409).

### List and get

`GET .../builds` returns the newest builds for the project, at most 50, under `builds`. A build id that is missing or belongs to another project is `PROJECT.BUILD_NOT_FOUND` (HTTP 404).

## Errors

Errors use the Skeleton API envelope from `skeleton/api/errors.py`. The checked router still emits `{"detail": "invalid_session"}` and the other `detail` strings. The moved router emits:

```json
{"error": {"type": "ProjectContractError", "code": "PROJECT.NOT_FOUND", "message": "project not found", "context": {}}}
```

| Code | HTTP | Checked `detail` | When |
|------|------|------------------|------|
| `PROJECT.UNAUTHENTICATED` | 401 | `invalid_session` | Missing or unknown bearer token |
| `PROJECT.INVALID` | 422 | validation error | Body or field rejection, including a blank brief |
| `PROJECT.NOT_FOUND` | 404 | `project_not_found` | Unknown project, or project owned by another session user |
| `PROJECT.BUILD_NOT_FOUND` | 404 | `build_not_found` | Unknown build on this project |
| `PROJECT.CONFLICT` | 409 | `project_name_conflict` | This owner already has that name |
| `PROJECT.BUILD_CONFLICT` | 409 | — | `execution_id` cannot be linked |

Context must not contain secret values.

## One schema

`skeleton/ai/runtime/contracts/projects.py` re-exports this module. Callers do not keep a second Projects shape. A handler that mounts these routes consumes `Project`, `Build`, and `project_error_envelope` rather than inventing fields.
