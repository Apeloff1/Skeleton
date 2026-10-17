# ADR-0003: Versioned subsystem contracts and the Projects resource

Status: **accepted**

Decision source: the app foundation client and frontend align to the Projects router Internal Systems is moving onto `/api/v1/projects`.

## Context

Kernel, agents, memory, GameForge, and the API already exchange data through a mix of Python dataclasses, machine protocol rows, and HTTP handlers. The app foundation client (auth, agents, builds, SSE parsing) and the frontend shell are landing against that surface. Builds are engine executions. The backend has no Projects routes, and the client therefore has no `ProjectsClient`.

Publishing a second Projects shape beside the #4097 router would fork the resource. The schema describes that router.

## Decision

`skeleton/contracts/subsystem_boundaries.py` publishes version `1.0.0` envelopes for kernel events, agent tasks, memory writes, the GameForge `run`/`intake` facade, and the API error object. GameForge pipeline internals stay behind a request digest.

`skeleton/contracts/projects.py`, `docs/architecture/contracts/projects.md`, and `docs/architecture/contracts/projects.schema.json` publish Projects schema `skeleton.projects.v1` at version `1.0.0`. That is the router on PR #4097 (`skeleton/api/projects_routes.py`, commit `959eec134`), mounted at `/api/v1/projects` inside `create_app` behind `install_gate`.

- `POST /api/v1/projects` creates a project from a string or a structured brief. The stored brief is the object. `Idempotency-Key` replays with 200 or returns `PROJECT.IDEMPOTENCY_MISMATCH`.
- `GET /api/v1/projects` is paginated (`limit`, `cursor`) and returns `{schema_version, items, next_cursor}`.
- `GET /api/v1/projects/{project_id}` returns one project. `actor_id` is the session user. `tenant_id` is `APP_TENANT_ID` (default `default`).
- `POST /api/v1/projects/{project_id}/builds` starts a `game.build` job and returns `Build` (`execution_id` equals `build_id`). A body that is only `execution_id` links that execution and returns `ProjectBuildLink`.
- `GET /api/v1/projects/{project_id}/builds` is paginated, newest first. `GET .../builds/{build_id}` returns one build.

Errors use `{error:{type, code:PROJECT.*, message, context}}`, including `PROJECT.NAME_CONFLICT`, `PROJECT.IDEMPOTENCY_MISMATCH`, and `PROJECT.UNAVAILABLE`. The job queue is `docs/contracts/job_queue.md`.

Health payloads keep their current JSON. `skeleton/contracts/health.py` parses them. Public configuration snapshots go through `skeleton/config/public_snapshot.py`.

## Consequences

The foundation client adds `ProjectsClient` against `PROJECT_ROUTES` and the `Project` / `Build` documents. A missing project and a project outside the session actor and tenant share `PROJECT.NOT_FOUND`.

## Amendment

An intermediate draft on this branch described a different resource (`owner_id`, epoch timestamps, version `1.1.0`). Commit `959eec134` is the implementation. The contract is version `1.0.0` and matches that router: string or structured brief, session-derived actor and tenant, start-build with optional `execution_id` link, paginated build list, `PROJECT.IDEMPOTENCY_MISMATCH`, and the `PROJECT.*` envelope.
